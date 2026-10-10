"""One-time setup: find tools, fetch the community templates, write config.ini."""
import os
import shutil
import sys
import urllib.request
import zipfile

from . import config
from .songs import find_ffmpeg
from .waapi import find_wwise_console

# Files from the community guide "Crime Boss Custom Tracks for the Wwise" and rtkzboss/set-container-id.
# They are downloaded from their original locations rather than bundled.
DOWNLOADS = [
    ("JukeboxTemplate", "drive", "1MjhssGyS4QYI1K3XGjqgZidAKIO_8SRz",
     "Unreal project that packages the audio (guide Part A)"),
    ("CrimeBossU18", "drive", "1lTQ0g02YjB0K2Ocb2_-VFtCaIKYOx6C-",
     "Unreal project that builds the UGC mod (guide Part B)"),
    ("JukeboxTransfer", "drive", "1Xq_8Mr6F8-OzS0n3xrxSU_lxAYcZN6LJ",
     "JukeboxMod files for the UGC project (guide Part B step 2)"),
    ("WwiseStates", "drive", "1_ADWOQvjCg6N6goXIYd4wXLP65oT9dlZ",
     "Crime Boss Wwise state definitions (reference only)"),
    ("set_container_id.exe", "url",
     "https://github.com/rtkzboss/set-container-id/releases/download/v0.1.1/set_container_id.exe",
     "Avoids conflicts between mods (guide Part C)"),
]


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def fetch_third_party(force=False):
    os.makedirs(config.THIRD_PARTY_DIR, exist_ok=True)
    for name, kind, ref, desc in DOWNLOADS:
        target = os.path.join(config.THIRD_PARTY_DIR, name)
        if os.path.exists(target) and not force:
            print(f"  [have]  {name}")
            continue
        print(f"  [get]   {name} - {desc}")
        if kind == "url":
            _download(ref, target)
            continue
        tmp = target + ".zip"
        _download(f"https://drive.usercontent.google.com/download?id={ref}&export=download&confirm=t", tmp)
        if not zipfile.is_zipfile(tmp):
            os.remove(tmp)
            print(f"          ! download failed (Google Drive may be rate-limiting). Try again later.")
            continue
        with zipfile.ZipFile(tmp) as z:
            z.extractall(target)
        os.remove(tmp)


NEVER_COOK = ['+DirectoriesToNeverCook=(Path="/JukeboxMod")', '+DirectoriesToNeverCook=(Path="/Game/JukeboxMod")']


def find_modkit_project(configured=None):
    candidates = [configured] if configured else []
    for drive in ("C:", "D:", "E:", "F:"):
        candidates += [rf"{drive}\CBModKit\CBModKit\CrimeBoss\CrimeBoss.uproject",
                       rf"{drive}\CBModKit\CrimeBoss\CrimeBoss.uproject",
                       rf"{drive}\Program Files\Epic Games\CrimeBossModKit\CrimeBoss\CrimeBoss.uproject",
                       rf"{drive}\Epic Games\CrimeBossModKit\CrimeBoss\CrimeBoss.uproject"]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def install_editor_plugin(uproject):
    """Copy the Jukebox menu plugin + the JukeboxMod dependency into the Mod Kit project."""
    proj = os.path.dirname(uproject)
    src = os.path.join(config.ROOT, "EditorPlugin", "JukeboxBuilder")
    dst = os.path.join(proj, "Plugins", "JukeboxBuilder")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    import json
    from .release import find_game_mods_dir
    game_mods = config.load()["paths"].get("game_mods_dir") or find_game_mods_dir() or ""
    with open(os.path.join(dst, "Content", "Python", "jukebox_config.json"), "w", encoding="utf-8") as f:
        json.dump({"builder_root": config.ROOT, "game_mods_dir": game_mods}, f, indent=2)
    print("  Game Mods folder: " + (game_mods or "not found (finished mods are left in Output\\<Mod>\\Release)"))
    print(f"  [ok]    Jukebox menu plugin -> {dst}")

    jm_src = os.path.join(config.THIRD_PARTY_DIR, "JukeboxTransfer", "Mods", "JukeboxMod")
    jm_dst = os.path.join(proj, "Mods", "JukeboxMod")
    if os.path.isdir(jm_dst):
        print("  [have]  Mods\\JukeboxMod")
    elif os.path.isdir(jm_src):
        shutil.copytree(jm_src, jm_dst)
        print("  [ok]    Mods\\JukeboxMod (needed so jukebox mods can reference CDT_Jukebox)")
    else:
        print("  ! JukeboxMod files missing - re-run Setup.bat when the downloads work")

    # Never cook the JukeboxMod content into individual mods (guide Part B step 3).
    ini = os.path.join(proj, "Config", "DefaultGame.ini")
    with open(ini, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    missing = [l for l in NEVER_COOK if l not in lines]
    if missing:
        try:
            i = lines.index("[/Script/UnrealEd.ProjectPackagingSettings]") + 1
        except ValueError:
            lines += ["", "[/Script/UnrealEd.ProjectPackagingSettings]"]
            i = len(lines)
        lines[i:i] = missing
        with open(ini, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        print("  [ok]    added /JukeboxMod to 'Directories to never cook' (Config\\DefaultGame.ini)")


def run():
    print("Jukebox Builder setup\n")
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is required.")
        return 1
    cp = config.load()
    paths = cp["paths"]

    wc = find_wwise_console(paths.get("wwise_console"))
    if wc:
        paths["wwise_console"] = wc
        print(f"  Wwise:  {wc}")
    else:
        print("  Wwise:  NOT FOUND. Install Wwise 2021.1.14 with the Audiokinetic Launcher,\n"
              "          or put the full path to WwiseConsole.exe in config.ini.")

    ff = find_ffmpeg(paths.get("ffmpeg"))
    if ff:
        paths["ffmpeg"] = ff
        print(f"  ffmpeg: {ff}")
    else:
        print("  ffmpeg: not found (optional - only needed for MP3/OGG/FLAC; WAV always works)")
    config.save(cp)

    print("\nDownloading templates and tools:")
    fetch_third_party()

    print("\nCrime Boss Mod Kit:")
    uproject = find_modkit_project(paths.get("modkit_project"))
    if not uproject:
        typed = input("  Mod Kit not found. Paste the full path to CrimeBoss.uproject (or press Enter to skip): ")
        typed = typed.strip().strip('"')
        uproject = typed if os.path.isfile(typed) else None
    if uproject:
        paths["modkit_project"] = uproject
        config.save(cp)
        print(f"  Mod Kit: {uproject}")
        install_editor_plugin(uproject)
        print("  Restart the Mod Kit editor to see the new 'Jukebox' menu.")
    else:
        print("  skipped - the Jukebox menu was not installed into the Mod Kit")

    os.makedirs(config.SONGS_DIR, exist_ok=True)
    print(f"\nDone. Put your songs in: {config.SONGS_DIR}")
    return 0 if wc else 1
