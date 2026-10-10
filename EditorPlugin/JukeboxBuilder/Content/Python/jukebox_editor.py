"""Jukebox menu for the Crime Boss Mod Kit.

Adds a "Jukebox" menu (main menu bar + toolbar) with:
  * Create Jukebox Mod...  - makes Mods/<Name> with the UGC blueprint and track DataTable set up
  * Open Songs Folder...   - where you drop the music for a mod
  * Build Jukebox Mod...   - one click: Wwise project, audio pak (headless, in the background),
                             track list. Then you press the Mod Kit's own Package Mod, and the
                             finished mod is assembled (guide Part C) and installed automatically.
  * Install into Game     - redo the final assembly/install by hand (normally automatic)

Python can't mount a brand new plugin in a running editor, so creating a mod writes the
files, restarts the editor, and finishes creating the assets on the next start.
"""
import json
import os
import re
import subprocess
import sys

import unreal

PLUGIN_PY_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PLUGIN_PY_DIR, "jukebox_config.json")

JUKEBOX_STRUCT = "/JukeboxMod/JukeboxStruct"
JUKEBOX_CDT = "/JukeboxMod/CDT_Jukebox"
JUKEBOX_PDA = "/JukeboxMod/PDA_JukeboxTrack"
# Where the audio project puts each song's PDA_JukeboxTrack (one sub-folder per mod).
TRACKS_ROOT = "/Game/JukeboxMod/Tracks"

MENU_OWNER = "JukeboxBuilder"
_tick_handle = None
_job = None          # the running/watched build: dict(mod, proc, phase, baseline, ...)
_job_tick = None


# --------------------------------------------------------------------------- paths & helpers

def _full(path):
    return os.path.normpath(unreal.Paths.convert_relative_path_to_full(path))


def project_dir():
    return _full(unreal.Paths.project_dir())


def mods_dir():
    return os.path.join(project_dir(), "Mods")


def state_dir():
    d = os.path.join(_full(unreal.Paths.project_saved_dir()), "JukeboxBuilder")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def builder_root():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            root = json.load(f).get("builder_root", "")
        return root if os.path.isdir(root) else None
    except (OSError, ValueError):
        return None


def editor_python():
    return os.path.join(_full(unreal.Paths.engine_dir()), "Binaries", "ThirdParty", "Python3", "Win64", "python.exe")


def track_asset_path(mod, song_id):
    return "{}/{}/PDA_{}".format(TRACKS_ROOT, mod, song_id)


def message(text, title="Jukebox Builder", kind=None):
    return unreal.EditorDialog.show_message(title, text, kind or unreal.AppMsgType.OK)


def _prefs():
    try:
        with open(os.path.join(state_dir(), "prefs.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_prefs(p):
    with open(os.path.join(state_dir(), "prefs.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)


def _dialog(mode, opts):
    """Show a Tk form in a separate process and return its JSON result (None if cancelled)."""
    res = subprocess.run([editor_python(), os.path.join(PLUGIN_PY_DIR, "jukebox_dialog.py"), mode, json.dumps(opts)],
                         capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if res.returncode != 0:
        unreal.log_error("Jukebox dialog failed: " + res.stderr)
        message("Could not open the dialog:\n\n" + res.stderr[-1500:])
        return None
    out = res.stdout.strip()
    return json.loads(out) if out else None


def existing_mod_names():
    d = mods_dir()
    return sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, n + ".uplugin"))) if os.path.isdir(d) else []


def jukebox_mods():
    """Mods made by this tool (they have a DT_<Name> next to the UGC blueprint)."""
    return [n for n in existing_mod_names()
            if os.path.isfile(os.path.join(mods_dir(), n, "Content", "DT_{}.uasset".format(n)))
            or os.path.isfile(os.path.join(state_dir(), "pending_{}.json".format(n)))]


def _pick_jukebox_mod(title):
    mods = jukebox_mods()
    if not mods:
        message("There are no jukebox mods yet. Use Jukebox > Create Jukebox Mod... first.")
        return None
    if len(mods) == 1:
        return mods[0]
    res = _dialog("choose", {"title": title, "prompt": "Which jukebox mod?", "items": mods})
    return res and res.get("choice")


# --------------------------------------------------------------------------- data validation

VALIDATOR_SECTION = "[/Script/DataValidation.EditorValidatorSubsystem]"


def ensure_validation_exclusions(names):
    """Skip 505's UGC validator for jukebox mods' UGC_ blueprint.

    The Mod Kit's validator insists a Data Table Extension's original table lives under /Game/,
    but the jukebox extends /JukeboxMod/CDT_Jukebox (a mod's table) - exactly what the guide does.
    The guide-era UGC plugin had no such check; it is editor-only, so we exclude just the UGC_
    asset using the engine's own ExcludedDirectories setting (substring match on package path).
    Takes effect on the next editor start. Returns True if the ini changed.
    """
    ini = os.path.join(project_dir(), "Config", "DefaultEditor.ini")
    try:
        with open(ini, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    wanted = ['+ExcludedDirectories=(Path="/{0}/UGC_{0}")'.format(n) for n in names]
    missing = [w for w in wanted if w not in lines]
    if not missing:
        return False
    if VALIDATOR_SECTION in lines:
        i = lines.index(VALIDATOR_SECTION) + 1
    else:
        lines += ["", VALIDATOR_SECTION]
        i = len(lines)
    lines[i:i] = missing
    with open(ini, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return True


# --------------------------------------------------------------------------- create mod

SONG_SECTIONS = ("stealth", "control", "assault")
AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".opus", ".wma")
HOW_TO = """Put this mod's music here.

One song:   drop the files into the stealth, control and assault folders.
            Files play in name order (01_, 02_ ...). A file with "loop" in its name loops forever;
            otherwise the last file in each folder loops.
More songs: make one folder per song here instead, each with its own stealth, control and
            assault folders (empty folders are ignored, so you can leave these three or delete them).

Then in the Mod Kit: Jukebox > Build Jukebox Mod.
See README.txt in the Jukebox Builder's Songs folder for more (loudness, extra sections...).
"""


def ensure_songs_folder(name):
    """Songs/<Mod> with stealth/control/assault ready to fill (only when the folder is new/empty)."""
    d = os.path.join(builder_root(), "Songs", name)
    if not os.path.isdir(d) or not os.listdir(d):
        for sec in SONG_SECTIONS:
            os.makedirs(os.path.join(d, sec), exist_ok=True)
        with open(os.path.join(d, "HOW TO.txt"), "w", encoding="utf-8") as f:
            f.write(HOW_TO)
    return d


def _has_audio(folder):
    for root, _, files in os.walk(folder):
        if any(f.lower().endswith(AUDIO_EXTS) for f in files):
            return True
    return False


UPLUGIN_TEMPLATE = {
    "FileVersion": 3, "Version": 1, "VersionName": "1.0", "FriendlyName": "", "Description": "",
    "Category": "CBUGC", "CreatedBy": "", "CreatedByURL": "", "DocsURL": "", "MarketplaceURL": "",
    "SupportURL": "", "CanContainContent": True, "IsBetaVersion": False, "IsExperimentalVersion": False,
    "Installed": False,
}


def create_mod_files(info):
    """Write the plugin skeleton the same way the built-in Create Mod wizard does."""
    name = info["name"]
    root = os.path.join(mods_dir(), name)
    os.makedirs(os.path.join(root, "Content"))
    os.makedirs(os.path.join(root, "Resources"))
    desc = dict(UPLUGIN_TEMPLATE, FriendlyName=name, Description=info.get("description", ""),
                CreatedBy=info.get("author", ""))
    with open(os.path.join(root, name + ".uplugin"), "w", encoding="utf-8") as f:
        json.dump(desc, f, indent="\t")
    icon = os.path.join(project_dir(), "Plugins", "CrimeBossUGC", "Templates", "BaseTemplate", "Resources", "Icon128.png")
    if os.path.isfile(icon):
        with open(icon, "rb") as src, open(os.path.join(root, "Resources", "Icon128.png"), "wb") as dst:
            dst.write(src.read())
    with open(os.path.join(state_dir(), "pending_{}.json".format(name)), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    ensure_validation_exclusions([name])  # active after the restart that follows
    br = builder_root()
    if br:
        ensure_songs_folder(name)


def populate_mod_assets(info):
    """Create UGC_<Name> and DT_<Name> inside the (now mounted) mod plugin."""
    name = info["name"]
    root = "/" + name
    eal = unreal.EditorAssetLibrary
    tools = unreal.AssetToolsHelpers.get_asset_tools()

    dt_path = "{}/DT_{}".format(root, name)
    if eal.does_asset_exist(dt_path):
        dt = eal.load_asset(dt_path)
    else:
        f = unreal.DataTableFactory()
        f.set_editor_property("struct", unreal.load_asset(JUKEBOX_STRUCT))
        dt = tools.create_asset("DT_" + name, root, unreal.DataTable, f)
        if dt is None:
            raise RuntimeError("could not create " + dt_path)
        eal.save_loaded_asset(dt, False)

    ugc_path = "{}/UGC_{}".format(root, name)
    if not eal.does_asset_exist(ugc_path):
        f = unreal.BlueprintFactory()
        f.set_editor_property("parent_class", unreal.IGS_UGCModBase)
        if tools.create_asset("UGC_" + name, root, unreal.Blueprint, f) is None:
            raise RuntimeError("could not create " + ugc_path)
    cdo = unreal.get_default_object(eal.load_blueprint_class(ugc_path))
    cdo.set_editor_property("mod_name", name)
    cdo.set_editor_property("author", info.get("author", ""))
    cdo.set_editor_property("description", info.get("description", ""))
    cdo.set_editor_property("version", info.get("version", "1.0.0") or "1.0.0")
    ext = unreal.IGS_ModTableExtension()
    ext.set_editor_property("original_data_table", unreal.load_asset(JUKEBOX_CDT))
    ext.set_editor_property("mod_data_table", dt)
    cdo.set_editor_property("data_table_extensions", [ext])
    eal.save_asset(ugc_path, False)


def _ensure_placeholder_track(mod, song):
    path = track_asset_path(mod, song["id"])
    eal = unreal.EditorAssetLibrary
    if eal.does_asset_exist(path):
        asset = eal.load_asset(path)
    else:
        f = unreal.DataAssetFactory()
        f.set_editor_property("data_asset_class", eal.load_blueprint_class(JUKEBOX_PDA))
        folder, asset_name = path.rsplit("/", 1)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(asset_name, folder, None, f)
        if asset is None:
            raise RuntimeError("could not create " + path)
    asset.set_editor_property("Name", song.get("display_name", song["id"]))
    eal.save_loaded_asset(asset, False)


def update_track_list(name, quiet=False):
    """Fill DT_<Name> with one row per song from the last Wwise build."""
    br = builder_root()
    manifest = os.path.join(br, "Output", name, "manifest.json") if br else None
    if not manifest or not os.path.isfile(manifest):
        if not quiet:
            message("No songs have been built for '{}' yet.\n\nPut your music in the songs folder "
                    "(Jukebox > Open Songs Folder...) and run Jukebox > Build Jukebox Mod... first.".format(name))
        return 0
    with open(manifest, encoding="utf-8") as f:
        songs = json.load(f)["songs"]
    # The DataTable holds hard references, so the track assets must exist in this project too
    # (guide Part B: "recreate the DataAssets ... just the location and the name"). /Game is never
    # cooked here, so these placeholders stay out of the mod; the real ones come from the audio pak.
    for s in songs:
        _ensure_placeholder_track(name, s)

    # CSV, because fill_data_table_from_json_string is broken in this engine build (it runs the CSV parser).
    lines = ["---,FolderToRead,JukeboxTrack"]
    for s in songs:
        path = track_asset_path(name, s["id"])
        lines.append('{},"","{}.{}"'.format(s["id"], path, path.rsplit("/", 1)[1]))
    rows = lines[1:]
    dt_path = "/{0}/DT_{0}".format(name)
    dt = unreal.EditorAssetLibrary.load_asset(dt_path)
    if dt is None:
        message("Could not find {}.".format(dt_path))
        return 0
    if not unreal.DataTableFunctionLibrary.fill_data_table_from_csv_string(dt, "\n".join(lines) + "\n"):
        message("Could not write the track list into {} (see Output Log).".format(dt_path))
        return 0
    unreal.EditorAssetLibrary.save_loaded_asset(dt, False)
    if not quiet:
        message("{} now lists {} song(s):\n\n{}".format(dt_path, len(rows), "\n".join(
            "  - {}".format(s.get("display_name", s["id"])) for s in songs)))
    return len(rows)


def restart_editor():
    """Save (asking the user), then relaunch the editor with the same project."""
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages_with_dialog(True, True):
        return False
    exe = os.path.join(_full(unreal.Paths.engine_dir()), "Binaries", "Win64", "UE4Editor.exe")
    uproject = _full(unreal.Paths.get_project_file_path())
    ps = ("Wait-Process -Id {pid} -ErrorAction SilentlyContinue; "
          "Start-Process -FilePath '{exe}' -ArgumentList '\"{proj}\"'").format(pid=os.getpid(), exe=exe, proj=uproject)
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    unreal.SystemLibrary.quit_editor()
    return True


# --------------------------------------------------------------------------- menu actions

def cmd_create_mod():
    prefs = _prefs()
    info = _dialog("create", {"existing": existing_mod_names(), "author": prefs.get("author", "")})
    if not info:
        return
    prefs["author"] = info.get("author", "")
    _save_prefs(prefs)
    try:
        create_mod_files(info)
    except OSError as e:
        message("Could not create the mod folder:\n\n{}".format(e))
        return
    answer = message("The mod '{}' was created in Mods\\{}.\n\nThe editor has to restart to load it. "
                     "It will finish setting the mod up (UGC_{} and DT_{}) when it opens again.\n\n"
                     "Restart now?".format(info["name"], info["name"], info["name"], info["name"]),
                     kind=unreal.AppMsgType.YES_NO)
    if answer == unreal.AppReturnType.YES:
        restart_editor()


def cmd_open_songs(name=None):
    name = name or _pick_jukebox_mod("Open Songs Folder")
    br = builder_root()
    if not name or not br:
        if not br:
            message("The Jukebox Builder folder could not be found. Run Setup.bat in the Jukebox Builder again.")
        return
    os.startfile(ensure_songs_folder(name))


# --------------------------------------------------------------------------- one-click build

def _builder_modules():
    """Import the Jukebox Builder's own Python package (shared code for Part C)."""
    br = builder_root()
    if not br:
        raise RuntimeError("The Jukebox Builder folder could not be found. Run Setup.bat again.")
    if br not in sys.path:
        sys.path.insert(0, br)
    import jukebox_builder.release as release
    return br, release


def _config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_watch():
    path = os.path.join(state_dir(), "watch.json")
    if _job and _job.get("phase") == "package":
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mod": _job["mod"], "baseline": _job["baseline"]}, f)
    elif os.path.isfile(path):
        os.remove(path)


def _published_mtime(release, name):
    files = release.published_ugc_files(project_dir(), name)
    return max(os.path.getmtime(p) for p in files.values()) if files else 0.0


def _start_ticking():
    global _job_tick
    if _job_tick is None:
        _job_tick = unreal.register_slate_post_tick_callback(_job_tick_fn)


def _stop_ticking():
    global _job_tick
    if _job_tick is not None:
        unreal.unregister_slate_post_tick_callback(_job_tick)
        _job_tick = None


def cmd_build_mod(name=None):
    global _job
    if _job and _job.get("phase") == "build":
        message("A jukebox build for '{}' is already running (see its console window).".format(_job["mod"]))
        return
    name = name or _pick_jukebox_mod("Build Jukebox Mod")
    if not name:
        return
    try:
        br, release = _builder_modules()
    except Exception as e:
        message(str(e))
        return
    songs = os.path.join(br, "Songs", name)
    if not _has_audio(songs):
        message("There's no music in the songs folder for '{}' yet.\n\nUse Jukebox > Open Songs Folder... "
                "and add your music first.".format(name))
        return
    status = os.path.join(br, "Output", name, "build_status.json")
    if os.path.isfile(status):
        os.remove(status)
    # The console shows progress; it stays open if something fails so the error can be read.
    cmd = 'set "PYTHONUTF8=1" && "{py}" -m jukebox_builder build "{songs}" --modkit "{proj}" || pause'.format(
        py=editor_python(), songs=songs, proj=_full(unreal.Paths.get_project_file_path()))
    proc = subprocess.Popen('cmd /c "{}"'.format(cmd), cwd=br, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    _job = {"mod": name, "proc": proc, "phase": "build", "status": status, "next": 0.0}
    _start_ticking()
    unreal.log("Jukebox Builder: building '{}'...".format(name))
    message("Building '{}' in the background - the progress is in the console window that just opened.\n\n"
            "This makes the Wwise project and the audio pak (a few minutes). You can keep working; "
            "you'll get a message here when it's done.".format(name))


def _job_tick_fn(_dt):
    global _job
    import time
    if not _job:
        _stop_ticking()
        return
    now = time.time()
    if now < _job.get("next", 0):
        return
    _job["next"] = now + 2.0
    try:
        if _job["phase"] == "build":
            _tick_build()
        elif _job["phase"] == "package":
            _tick_package()
    except Exception as e:
        unreal.log_error("Jukebox Builder: {}".format(e))
        message("Jukebox build for '{}' stopped:\n\n{}".format(_job["mod"], e))
        _job = None
        _save_watch()
        _stop_ticking()


def _tick_build():
    global _job
    if _job["proc"].poll() is None:
        return
    name = _job["mod"]
    try:
        with open(_job["status"], encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {"state": "failed", "message": "The build window was closed before it finished."}
    if st.get("state") != "done":
        _job = None
        _stop_ticking()
        message("Building '{}' failed:\n\n{}\n\nLogs: JukeboxBuilder\\Output\\{}\\logs".format(
            name, st.get("message", "unknown error")[:1500], name))
        return
    count = update_track_list(name, quiet=True)
    _, release = _builder_modules()
    _job.update(phase="package", baseline=_published_mtime(release, name))
    _save_watch()
    message("'{}' audio is built and DT_{} lists {} song(s).\n\n"
            "Last step: package the mod as usual - Package Mod > {}.\n\n"
            "When packaging finishes, Jukebox Builder puts the final mod together (UGC pak + audio pak) "
            "and offers to install it into the game.".format(name, name, count, name))


def _tick_package():
    _, release = _builder_modules()
    name = _job["mod"]
    files = release.published_ugc_files(project_dir(), name)
    if not files:
        return
    mtime = max(os.path.getmtime(p) for p in files.values())
    size = sum(os.path.getsize(p) for p in files.values())
    if mtime <= _job["baseline"]:
        return
    import time
    # Wait until the packager has stopped writing (unchanged for one poll and a few seconds old).
    if _job.get("last_size") != size or time.time() - mtime < 5:
        _job["last_size"] = size
        return
    finish_mod(name)


def finish_mod(name, ask_install=True):
    global _job
    br, release = _builder_modules()
    if _job and _job.get("mod") == name:
        _job = None
        _save_watch()
        _stop_ticking()
    try:
        rel = release.assemble(name, project_dir(), os.path.join(br, "Output", name))
    except Exception as e:
        message(str(e))
        return
    cfg = _config()
    game_mods = cfg.get("game_mods_dir") or release.find_game_mods_dir()
    text = "'{}' is finished:\n\n{}".format(name, rel)
    if ask_install and game_mods and os.path.isdir(game_mods):
        target = os.path.join(game_mods, name)
        verb = "Replace" if os.path.isdir(target) else "Install"
        if message(text + "\n\n{} it in the game now?\n{}".format(verb, target),
                   kind=unreal.AppMsgType.YES_NO) == unreal.AppReturnType.YES:
            try:
                release.install(rel, game_mods)
                message("Installed to:\n{}\n\nStart the game and pick the track in the jukebox. "
                        "Players also need JukeboxMod installed.".format(target))
            except OSError as e:
                message("Could not install (is the game running?):\n\n{}".format(e))
            return
    else:
        message(text + "\n\nCopy that folder into the game's CrimeBoss\\Mods folder to play it.")
    os.startfile(rel)


def cmd_finish_mod(name=None):
    name = name or _pick_jukebox_mod("Install into Game")
    if name:
        finish_mod(name)


def cmd_show_logs(name=None):
    name = name or _pick_jukebox_mod("Open Build Folder")
    br = builder_root()
    if name and br:
        d = os.path.join(br, "Output", name)
        os.startfile(d if os.path.isdir(d) else br)


def _resume_watch():
    """Keep watching for Package Mod after an editor restart."""
    global _job
    path = os.path.join(state_dir(), "watch.json")
    try:
        with open(path, encoding="utf-8") as f:
            w = json.load(f)
        _job = {"mod": w["mod"], "phase": "package", "baseline": w["baseline"], "next": 0.0}
        _start_ticking()
    except (OSError, ValueError, KeyError):
        pass


def cmd_about():
    br = builder_root() or "(not found - run Setup.bat again)"
    message("Jukebox Builder\n\nTool folder: {}\nTracks are referenced from: {}/<ModName>/\n\n"
            "Steps:\n 1. Create Jukebox Mod\n 2. Open Songs Folder and add your music\n"
            " 3. Build Jukebox Mod (runs in the background)\n 4. Package Mod > your mod, as usual\n"
            " 5. The finished mod is put together and you're offered to install it".format(br, TRACKS_ROOT))


# --------------------------------------------------------------------------- startup

def _process_pending(_dt):
    global _tick_handle
    if unreal.AssetRegistryHelpers.get_asset_registry().is_loading_assets():
        return
    unreal.unregister_slate_post_tick_callback(_tick_handle)
    _tick_handle = None
    done, failed = [], []
    for fn in sorted(os.listdir(state_dir())):
        m = re.match(r"pending_(\w+)\.json$", fn)
        if not m:
            continue
        path = os.path.join(state_dir(), fn)
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
        if not unreal.EditorAssetLibrary.does_directory_exist("/" + info["name"]):
            continue  # plugin not mounted (yet)
        try:
            populate_mod_assets(info)
            update_track_list(info["name"], quiet=True)
            os.remove(path)
            done.append(info["name"])
        except Exception as e:
            unreal.log_error("Jukebox Builder: setting up {} failed: {}".format(info["name"], e))
            failed.append("{}: {}".format(info["name"], e))
    if done:
        unreal.EditorAssetLibrary.sync_browser_to_objects(["/{0}/UGC_{0}".format(n) for n in done])
        message("Jukebox mod ready: {}\n\nNext: Jukebox > Open Songs Folder... and drop your music in.".format(
            ", ".join(done)))
    if failed:
        message("Some jukebox mods could not be set up:\n\n" + "\n".join(failed))


def _entry(name, label, tooltip, command):
    e = unreal.ToolMenuEntry(name=name, type=unreal.MultiBlockType.MENU_ENTRY)
    e.set_label(label)
    e.set_tool_tip(tooltip)
    e.set_string_command(unreal.ToolMenuStringCommandType.PYTHON, "", "import jukebox_editor; jukebox_editor." + command)
    return e


# (section, name, label, tooltip, command) - "{mod}" entries become a submenu listing every jukebox mod
ENTRIES = [
    ("Create", "JukeboxCreate", "Create Jukebox Mod...", "Create a new mod that adds custom heist music", "cmd_create_mod()"),
    ("Create", "JukeboxOpenSongs", "Open Songs Folder", "Open the folder where a mod's music goes", "cmd_open_songs({mod})"),
    ("Build", "JukeboxBuild", "Build Jukebox Mod",
     "Build the music (Wwise + audio pak) and the track list. Then press Package Mod; the rest is automatic.",
     "cmd_build_mod({mod})"),
    ("Build", "JukeboxFinish", "Install into Game",
     "Normally automatic after Package Mod: combines the packaged mod with its audio pak and copies it "
     "into the game's Mods folder. Use this to do it again by hand.", "cmd_finish_mod({mod})"),
    ("Help", "JukeboxLogs", "Open Build Folder", "Logs and outputs of a mod's last build", "cmd_show_logs({mod})"),
    ("Help", "JukeboxAbout", "About Jukebox Builder", "Where things are and what to do next", "cmd_about()"),
]


def _fill(menu):
    sections = {"Create": "Mod", "Build": "Build", "Help": "Help"}
    for sec, label in sections.items():
        menu.add_section(sec, label)
    mods = jukebox_mods()
    for sec, name, label, tip, cmd in ENTRIES:
        if "{mod}" not in cmd:
            menu.add_menu_entry(sec, _entry(name, label, tip, cmd))
            continue
        sub = menu.add_sub_menu(MENU_OWNER, sec, name, label, tip)
        sub.add_section("Mods", "Jukebox mods")
        for m in mods:
            sub.add_menu_entry("Mods", _entry(name + "_" + m, m, tip, cmd.format(mod=repr(m))))
        if not mods:
            sub.add_menu_entry("Mods", _entry(name + "_none", "(no jukebox mods yet - Create Jukebox Mod first)",
                                              tip, cmd.format(mod="")))


def register_menus():
    menus = unreal.ToolMenus.get()
    main = menus.find_menu("LevelEditor.MainMenu")
    if main:
        sub = main.add_sub_menu(MENU_OWNER, "", "Jukebox", "Jukebox", "Custom heist music mods")
        _fill(sub)
    try:
        combo_menu = menus.register_menu("LevelEditor.LevelEditorToolBar.JukeboxCombo", "", unreal.MultiBoxType.MENU, False)
        _fill(combo_menu)
        bar = menus.extend_menu("LevelEditor.LevelEditorToolBar")
        combo = unreal.ToolMenuEntry(name="JukeboxCombo", type=unreal.MultiBlockType.TOOL_BAR_COMBO_BUTTON)
        combo.set_label("Jukebox")
        combo.set_tool_tip("Custom heist music mods")
        combo.set_icon("EditorStyle", "ClassIcon.AmbientSound")
        bar.add_menu_entry("Settings", combo)
    except Exception as e:
        unreal.log_warning("Jukebox Builder: toolbar button not added ({})".format(e))
    menus.refresh_all_widgets()


def startup():
    global _tick_handle
    if "-run=" in unreal.SystemLibrary.get_command_line().lower():
        return  # commandlets (cooking, packaging, scripts) don't need menus
    register_menus()
    try:
        if ensure_validation_exclusions(jukebox_mods()):
            unreal.log_warning("Jukebox Builder: excluded jukebox UGC_ blueprints from the UGC validator. "
                               "Restart the editor for this to take effect.")
    except Exception as e:
        unreal.log_warning("Jukebox Builder: could not update DefaultEditor.ini ({})".format(e))
    _resume_watch()
    if any(f.startswith("pending_") for f in os.listdir(state_dir())):
        _tick_handle = unreal.register_slate_post_tick_callback(_process_pending)
    unreal.log("Jukebox Builder ready (Jukebox menu).")
