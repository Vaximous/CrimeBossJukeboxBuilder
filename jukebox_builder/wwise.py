"""Builds the Wwise project for a jukebox mod (Part A / "Step 01" of the guide).

Most objects are created through WAAPI with Wwise running headless. The few things
WAAPI 2021.1 cannot do (music-switch state paths, playlist loop counts, transition
timing, Vorbis codec) are written straight into the saved .wwu XML afterwards, then
the project is validated by generating a SoundBank with WwiseConsole.
"""
import glob
import json
import os
import random
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET

from .songs import ALL_MISSION_STATES, TRANSITIONS, _section_of, load_song, looks_like_song
from .waapi import WaapiServer

MMH = "\\Master-Mixer Hierarchy\\Default Work Unit\\Master Audio Bus"
STATES_WU = "\\States\\Default Work Unit"
CONV_WU = "\\Conversion Settings\\Default Work Unit"
IMH_WU = "\\Interactive Music Hierarchy\\Default Work Unit"
EVENTS_WU = "\\Events\\Default Work Unit"
BANKS_WU = "\\SoundBanks\\Default Work Unit"

JUKEBOX_WU = "Jukebox"
STATE_GROUP = "StateGrp_MissionState"
BUS_NAME = "Music_FPS"
BUS_VOLUME = -13
CHECK_BANK = "JukeboxBuilder_Check"


def log(msg=""):
    print(msg, flush=True)


def _guid():
    return "{" + str(uuid.uuid4()).upper() + "}"


def _short_id(used):
    while True:
        v = random.randint(1, 2**32 - 1)
        if v not in used:
            used.add(v)
            return str(v)


# --------------------------------------------------------------------------- XML helpers

def _read_xml(path):
    return ET.parse(path)


def _indent(elem, level=0):
    """Tab-indent in place (ET.indent needs Python 3.9; the editor ships 3.7)."""
    pad = "\n" + "\t" * level
    if len(elem):
        if not (elem.text or "").strip():
            elem.text = pad + "\t"
        for child in elem:
            _indent(child, level + 1)
        if not (child.tail or "").strip():
            child.tail = pad
    if level and not (elem.tail or "").strip():
        elem.tail = pad


def _write_xml(tree, path):
    for e in tree.getroot().iter():  # drop old whitespace so re-indenting is clean
        if e.text is not None and not e.text.strip():
            e.text = None
        if e.tail is not None and not e.tail.strip():
            e.tail = None
    _indent(tree.getroot())
    data = ET.tostring(tree.getroot(), encoding="unicode")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n' + data + "\n")


def _insert_ordered(parent, new, order):
    """Insert `new` among parent's children respecting Wwise's element order."""
    rank = order.index(new.tag)
    for i, ch in enumerate(list(parent)):
        if ch.tag in order and order.index(ch.tag) > rank:
            parent.insert(i, new)
            return new
    parent.append(new)
    return new


def _replace_child(parent, tag, order):
    old = parent.find(tag)
    if old is not None:
        parent.remove(old)
    return _insert_ordered(parent, ET.Element(tag), order)


def _prop(plist, name, typ, value):
    for p in plist.findall("Property"):
        if p.get("Name") == name:
            plist.remove(p)
    ET.SubElement(plist, "Property", Name=name, Type=typ, Value=str(value))


CONTAINER_ORDER = ["Comment", "PropertyList", "ReferenceList", "ChildrenList", "TransitionList",
                   "ObjectLists", "Playlist", "ArgumentList", "EntryList"]
TRANSITION_ORDER = ["PropertyList", "ReferenceList", "ChildrenList", "TransitionInfo"]


# --------------------------------------------------------------------------- WAAPI phase

def _ensure_shared(w):
    """Bus, state group and Jukebox work units. Returns ids we need later."""
    ids = {}
    music = w.create(MMH, "Bus", "Music")
    bus = w.create(music["id"], "Bus", BUS_NAME)
    w.set_property(bus["id"], "Volume", BUS_VOLUME)
    ids["bus"] = bus["id"]

    wu = w.create(STATES_WU, "WorkUnit", "WU_GameState")
    grp = w.create(wu["id"], "StateGroup", STATE_GROUP)
    ids["state_group"] = grp["id"]
    for s in ALL_MISSION_STATES:
        w.create(grp["id"], "State", s)
    ids["states"] = {c["name"]: c["id"] for c in w.children(grp["id"])}

    ids["imh_wu"] = w.create(IMH_WU, "WorkUnit", JUKEBOX_WU)["id"]
    ids["events_wu"] = w.create(EVENTS_WU, "WorkUnit", JUKEBOX_WU)["id"]
    return ids


def _sync_song(w, song, ids, conversions):
    sw = w.create(ids["imh_wu"], "MusicSwitchContainer", song.id, on_conflict="replace")
    w.set_reference(sw["id"], "OutputBus", ids["bus"])
    w.set_reference(sw["id"], "Conversion", conversions[song.quality])
    if song.volume_db:
        w.set_property(sw["id"], "Volume", song.volume_db)
    w.set_property(sw["id"], "Tempo", song.tempo)
    w.set_property(sw["id"], "TimeSignatureUpper", song.time_sig[0])
    w.set_property(sw["id"], "TimeSignatureLower", song.time_sig[1])

    info = {"switch": sw["id"], "sections": {}}
    imports = []
    for sec, pieces in song.sections.items():
        pl = w.create(sw["id"], "MusicPlaylistContainer", sec)
        info["sections"][sec] = {"id": pl["id"], "pieces": pieces}
        for p in pieces:
            imports.append({
                "audioFile": os.path.abspath(p.path),
                "objectPath": f"{IMH_WU}\\<WorkUnit>{JUKEBOX_WU}\\<MusicSwitchContainer>{song.id}"
                              f"\\<MusicPlaylistContainer>{sec}\\<MusicSegment>{p.name}",
                "originalsSubFolder": song.id,
            })
    w.call("ak.wwise.core.audio.import", {"importOperation": "replaceExisting",
                                          "default": {"importLanguage": "SFX"},
                                          "imports": imports, "autoAddToSourceControl": False})
    for sec, d in info["sections"].items():
        by_name = {c["name"]: c["id"] for c in w.children(d["id"]) if c["type"] == "MusicSegment"}
        d["segments"] = [(p, by_name[p.name]) for p in d["pieces"]]
        # Loudness: per-piece normalize gain on each segment, per-section volume on the playlist.
        for p, seg_id in d["segments"]:
            if p.gain_db:
                w.set_property(seg_id, "Volume", p.gain_db)
        if song.section_volume.get(sec):
            w.set_property(d["id"], "Volume", song.section_volume[sec])

    ev = w.create(ids["events_wu"], "Event", song.event_name, on_conflict="replace")
    act = w.create(ev["id"], "Action", "", on_conflict="rename")
    w.set_property(act["id"], "ActionType", 1)  # Play
    w.set_reference(act["id"], "Target", sw["id"])
    info["event"] = ev["id"]
    return info


def _remove_stale(w, ids, songs, conversions):
    """Delete songs/events/conversions from earlier builds that are no longer wanted.
    Returns the ids of removed songs so their Originals folders can be cleaned up."""
    keep = {s.id for s in songs}
    removed = []
    for c in w.children(ids["imh_wu"]):
        if c["name"] not in keep:
            log(f"  removing old song '{c['name']}'")
            w.delete(c["id"])
            removed.append(c["name"])
    for c in w.children(CONV_WU):
        if c["name"].startswith("Jukebox_Vorbis_") and c["id"] not in conversions.values():
            w.delete(c["id"])
    keep_ev = {s.event_name for s in songs}
    for c in w.children(ids["events_wu"]):
        if c["name"] not in keep_ev:
            w.delete(c["id"])
    return removed


# --------------------------------------------------------------------------- XML phase

def _patch_music(project_dir, songs, ids, infos):
    path = os.path.join(project_dir, "Interactive Music Hierarchy", f"{JUKEBOX_WU}.wwu")
    tree = _read_xml(path)
    root = tree.getroot()
    used = {int(e.get("ShortID")) for e in root.iter() if e.get("ShortID", "").isdigit()}
    wu_id = ids["imh_wu"]

    for song in songs:
        info = infos[song.id]
        sw = next(e for e in root.iter("MusicSwitchContainer") if e.get("ID") == info["switch"])

        # --- State group -> section associations (the "Association editor" step)
        args = _replace_child(sw, "ArgumentList", CONTAINER_ORDER)
        ET.SubElement(args, "ArgumentRef", Name=STATE_GROUP, ID=ids["state_group"])
        entries = _replace_child(sw, "EntryList", CONTAINER_ORDER)
        for state, sec in song.state_targets().items():
            e = ET.SubElement(entries, "Entry")
            ET.SubElement(ET.SubElement(e, "Path"), "PathElementRef", Name=state, ID=ids["states"][state])
            ET.SubElement(ET.SubElement(e, "AudioNodeInfo"), "AudioNodeRef", Name=sec,
                          ID=info["sections"][sec]["id"], WorkUnitID=wu_id, Platform="Linked")

        # --- Transition timing (Any -> Any rule under the root transition)
        root_tr = sw.find("TransitionList/MusicTransition")
        rule = root_tr.find("ChildrenList/MusicTransition")
        if rule is None:
            rule = ET.SubElement(_insert_ordered(root_tr, ET.Element("ChildrenList"), TRANSITION_ORDER),
                                 "MusicTransition", Name="Transition", ID=_guid())
            ET.SubElement(rule, "TransitionInfo")
        plist = rule.find("PropertyList")
        if plist is None:
            plist = _insert_ordered(rule, ET.Element("PropertyList"), TRANSITION_ORDER)
        _prop(plist, "ExitSourceAt", "int16", TRANSITIONS[song.transition])
        if song.fade_out_ms > 0:
            _prop(plist, "EnableSourceFadeOut", "bool", "True")
            tinfo = rule.find("TransitionInfo")
            if tinfo is None:
                tinfo = _insert_ordered(rule, ET.Element("TransitionInfo"), TRANSITION_ORDER)
            for old in tinfo.findall("SourceFadeOut"):
                tinfo.remove(old)
            fade = ET.SubElement(ET.SubElement(tinfo, "SourceFadeOut"), "MusicFade",
                                 Name="Source Fade-out", ID=_guid())
            fp = ET.SubElement(fade, "PropertyList")
            _prop(fp, "FadeTime", "Real64", round(song.fade_out_ms / 1000.0, 4))

        # --- Playlists: play pieces in order, loop the looping ones forever
        for sec, d in info["sections"].items():
            pl = next(e for e in sw.iter("MusicPlaylistContainer") if e.get("ID") == d["id"])
            playlist = pl.find("Playlist")
            if playlist is None:
                playlist = _insert_ordered(pl, ET.Element("Playlist"), CONTAINER_ORDER)
            top = playlist.find("MusicPlaylistItem")
            if top is None:
                top = ET.SubElement(playlist, "MusicPlaylistItem", Name="", ID=_guid(), ShortID=_short_id(used))
            for old in top.findall("ChildrenList"):
                top.remove(old)
            kids = ET.SubElement(top, "ChildrenList")
            for piece, seg_id in d["segments"]:
                item = ET.SubElement(kids, "MusicPlaylistItem", Name="", ID=_guid(), ShortID=_short_id(used))
                ip = ET.SubElement(item, "PropertyList")
                if piece.loop:
                    _prop(ip, "LoopCount", "int16", 0)  # 0 = infinite
                _prop(ip, "PlaylistItemType", "int16", 1)  # segment
                ET.SubElement(item, "SegmentRef", Name=piece.name, ID=seg_id)

    _write_xml(tree, path)


def _patch_conversions(project_dir, conversions):
    """Switch our conversion share-sets from PCM to Vorbis at the requested quality."""
    for path in glob.glob(os.path.join(project_dir, "Conversion Settings", "*.wwu")):
        tree = _read_xml(path)
        changed = False
        for conv in tree.getroot().iter("Conversion"):
            quality = next((q for q, cid in conversions.items() if cid == conv.get("ID")), None)
            if quality is None:
                continue
            plist = conv.find("PropertyList")
            if plist is None:
                plist = ET.Element("PropertyList")
                conv.insert(0, plist)
            for p in plist.findall("Property"):
                if p.get("Name") == "SRConversionQuality":
                    plist.remove(p)
            p = ET.SubElement(plist, "Property", Name="SRConversionQuality", Type="int32")
            ET.SubElement(ET.SubElement(p, "ValueList"), "Value", Platform="Windows").text = "1"  # High
            for old in conv.findall("ConversionPluginInfoList"):
                conv.remove(old)
            info = ET.SubElement(ET.SubElement(conv, "ConversionPluginInfoList"),
                                 "ConversionPluginInfo", Platform="Windows")
            plug = ET.SubElement(info, "ConversionPlugin", Name="", ID=_guid(), PluginName="Vorbis",
                                 CompanyID="0", PluginID="4")
            pp = ET.SubElement(plug, "PropertyList")
            _prop(pp, "QualityFactor", "Real32", quality)
            changed = True
        if changed:
            _write_xml(tree, path)


# --------------------------------------------------------------------------- validation

def _validate(wwise_console, wproj, out_dir, log_path):
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    cmd = [wwise_console, "generate-soundbank", wproj, "--platform", "Windows",
           "--bank", CHECK_BANK, "--soundbank-path", "Windows", out_dir]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(res.stdout + res.stderr)
    problems = [ln.strip() for ln in (res.stdout + res.stderr).splitlines()
                if re.search(r"\b(Error|Warning|Fatal)\b", ln) and "0 error" not in ln.lower()]
    banks = glob.glob(os.path.join(out_dir, "**", f"{CHECK_BANK}.bnk"), recursive=True)
    size = os.path.getsize(banks[0]) if banks else None
    return res.returncode, problems, size


# --------------------------------------------------------------------------- entry point

def find_song_dirs(mod_dir):
    """Song folders of a mod: the mod folder itself for a one-song mod, else its sub-folders."""
    if looks_like_song(mod_dir):
        return [mod_dir]  # single-song mod: stealth/control/assault directly in the mod folder
    # One folder per song. Leftover empty stealth/control/assault folders are skipped.
    return [os.path.join(mod_dir, d) for d in sorted(os.listdir(mod_dir))
            if os.path.isdir(os.path.join(mod_dir, d)) and not d.startswith(("_", "."))
            and not _section_of(d)]


def build_mod(mod_dir, output_root, wwise_console, ffmpeg=None):
    mod_name = os.path.basename(os.path.normpath(mod_dir))
    work = os.path.join(output_root, mod_name)
    # Wwise requires <Name>\<Name>.wproj
    project_dir = os.path.join(work, f"{mod_name}_Wwise")
    wproj = os.path.join(project_dir, f"{mod_name}_Wwise.wproj")
    os.makedirs(work, exist_ok=True)

    log(f"== {mod_name}")
    song_dirs = find_song_dirs(mod_dir)
    if not song_dirs:
        raise RuntimeError(f"'{mod_dir}' has no song folders inside it.")
    songs = []
    for d in song_dirs:
        s = load_song(d, work, ffmpeg)
        songs.append(s)
        parts = ", ".join(f"{k}: {len(v)} file(s)" for k, v in s.sections.items())
        log(f"  song '{s.display_name}' -> event {s.event_name}  [{parts}]")
        for wmsg in s.warnings:
            log(f"    ! {wmsg}")
    if len({s.id for s in songs}) != len(songs):
        raise RuntimeError("Two song folders end up with the same name after removing special characters.")

    if not os.path.exists(wproj):
        log("  creating Wwise project...")
        res = subprocess.run([wwise_console, "create-new-project", wproj, "--platform", "Windows"],
                             capture_output=True, text=True, errors="replace",
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if res.returncode != 0 or not os.path.exists(wproj):
            raise RuntimeError("Could not create the Wwise project:\n" + res.stdout + res.stderr)

    log("  starting Wwise (headless)...")
    with WaapiServer(wwise_console, wproj, os.path.join(work, "wwise_server.log")) as w:
        ids = _ensure_shared(w)
        conversions = {}
        for q in sorted({s.quality for s in songs}):
            name = f"Jukebox_Vorbis_Q{q:g}".replace(".", "_").replace("-", "m")
            conversions[q] = w.create(CONV_WU, "Conversion", name)["id"]
        removed = _remove_stale(w, ids, songs, conversions)
        infos = {}
        for s in songs:
            log(f"  importing '{s.display_name}'...")
            infos[s.id] = _sync_song(w, s, ids, conversions)
        bank = w.create(BANKS_WU, "SoundBank", CHECK_BANK, on_conflict="replace")
        w.call("ak.wwise.core.soundbank.setInclusions", {
            "soundbank": bank["id"], "operation": "replace",
            "inclusions": [{"object": i["event"], "filter": ["events", "structures", "media"]}
                           for i in infos.values()]})
        w.call("ak.wwise.core.project.save")

    for name in removed:
        shutil.rmtree(os.path.join(project_dir, "Originals", "SFX", name), ignore_errors=True)
        shutil.rmtree(os.path.join(work, "_converted", name), ignore_errors=True)

    log("  writing state associations, loops, transitions and Vorbis settings...")
    _patch_music(project_dir, songs, ids, infos)
    _patch_conversions(project_dir, conversions)

    log("  checking the project by building a test SoundBank...")
    code, problems, size = _validate(wwise_console, wproj, os.path.join(work, "_check"),
                                     os.path.join(work, "wwise_check.log"))
    for p in problems:
        log(f"    {p}")
    if code != 0 or size is None:
        raise RuntimeError(f"Wwise reported a problem (exit code {code}). See {os.path.join(work, 'wwise_check.log')}")
    with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"mod": mod_name, "wwise_project": wproj,
                   "songs": [{"id": s.id, "display_name": s.display_name, "event": s.event_name,
                              "sections": sorted(s.sections)} for s in songs]}, f, indent=2)
    pretty = f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{size / 1024:.0f} KB"
    log(f"  OK - all songs together are {pretty} after compression")
    log(f"  Wwise project: {wproj}")
    return wproj, songs
