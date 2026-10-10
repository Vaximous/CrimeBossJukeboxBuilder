"""Runs inside the audio project's headless editor (-run=pythonscript).

Creates one PDA_JukeboxTrack per song at <tracks_root>/<Mod>/PDA_<SongId>, links its Wwise
event, and points PAL_JukeboxTrack (chunk 999) at the tracks, events and media so they all
land in pakchunk999 (the guide's collection step).
"""
import json
import os

import unreal

job = json.load(open(os.environ["JUKEBOX_JOB"], encoding="utf-8"))
errors = []
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ar = unreal.AssetRegistryHelpers.get_asset_registry()
ar.scan_paths_synchronous(["/Game", "/JukeboxMod"], True)

pda_class = eal.load_blueprint_class("/JukeboxMod/PDA_JukeboxTrack")
labelled = []
for s in job["songs"]:
    ev_path = "{}/{}".format(job["events_root"], s["event"])
    ev = unreal.load_asset(ev_path)
    if ev is None:
        errors.append("event not found: " + ev_path)
        continue
    folder = "{}/{}".format(job["tracks_root"], job["mod"])
    name = "PDA_" + s["id"]
    if eal.does_asset_exist(folder + "/" + name):
        pda = eal.load_asset(folder + "/" + name)
    else:
        f = unreal.DataAssetFactory()
        f.set_editor_property("data_asset_class", pda_class)
        pda = tools.create_asset(name, folder, None, f)
    if pda is None:
        errors.append("could not create {}/{}".format(folder, name))
        continue
    pda.set_editor_property("Name", s["display_name"])
    pda.set_editor_property("AudioEvent", ev)
    pda.set_editor_property("IsBaseGameTrack", False)
    if not eal.save_loaded_asset(pda, False):
        errors.append("could not save " + name)
    labelled += [pda, ev]

media = [unreal.load_asset(str(a.package_name))
         for a in ar.get_assets_by_path("/Game/WwiseAudio/GeneratedSoundData/SoundBanks/Media", True)]
pal = unreal.load_asset("/Game/JukeboxMod/PAL_JukeboxTrack")
rules = pal.get_editor_property("rules")
rules.set_editor_property("bApplyRecursively", True)
pal.set_editor_property("rules", rules)
pal.set_editor_property("explicit_assets", labelled + [m for m in media if m])
coll = pal.get_editor_property("asset_collection")
coll.set_editor_property("collection_name", "None")
pal.set_editor_property("asset_collection", coll)
if not eal.save_loaded_asset(pal, False):
    errors.append("could not save PAL_JukeboxTrack")
if rules.get_editor_property("chunk_id") != 999:
    errors.append("PAL_JukeboxTrack is not set to chunk 999")

with open(job["result"], "w", encoding="utf-8") as f:
    json.dump({"errors": errors, "media": len(media)}, f)
