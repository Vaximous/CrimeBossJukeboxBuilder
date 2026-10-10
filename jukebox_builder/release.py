"""Part C of the guide: combine the packaged UGC mod with the audio pak and install it.

Final layout (same as working jukebox mods in the wild):
  <Mod>\\Content\\Paks\\WindowsNoEditor\\<Mod>CrimeBoss-WindowsNoEditor.pak/.ucas/.utoc   (Package Mod)
  <Mod>\\Content\\Paks\\WindowsNoEditor\\<Mod>CrimeBossAudio.pak/.ucas/.utoc             (audio pak)
"""
import os
import shutil

PAK_EXTS = ("pak", "ucas", "utoc")
PAKS_REL = os.path.join("Content", "Paks", "WindowsNoEditor")


def published_ugc_files(modkit_project_dir, mod):
    d = os.path.join(modkit_project_dir, "Mods", mod, "Publish", "WindowsNoEditor", "CrimeBoss", "Mods", mod, PAKS_REL)
    files = {e: os.path.join(d, "{}CrimeBoss-WindowsNoEditor.{}".format(mod, e)) for e in PAK_EXTS}
    return files if all(os.path.isfile(p) for p in files.values()) else None


DEV_REGISTRY = "Metadata/DevelopmentAssetRegistry.bin"


def _unrealpak(modkit_project_dir):
    p = os.path.normpath(os.path.join(modkit_project_dir, "..", "UnrealEngine", "Engine", "Binaries", "Win64",
                                      "UnrealPak.exe"))
    return p if os.path.isfile(p) else None


def _pak_list(unrealpak, pak):
    import re
    import subprocess
    res = subprocess.run([unrealpak, pak, "-List"], capture_output=True, text=True, errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    mount = re.search(r"Mount point (\S+)", res.stdout)
    files = re.findall(r'Display: "([^"]+)" offset: \d+, size: \d+ bytes, sha1: \w+, compression: (\w+)', res.stdout)
    return (mount.group(1) if mount else None), files


def strip_dev_registry(pak, unrealpak):
    """Rebuild a UGC .pak without Metadata/DevelopmentAssetRegistry.bin.

    505's Package Mod puts this editor-only debug file (~20 MB) into every mod; the game
    doesn't need it. Same mount point, paths and compression otherwise. Returns bytes saved
    (0 if there was nothing to strip).
    """
    import subprocess
    import tempfile
    mount, files = _pak_list(unrealpak, pak)
    if not mount or DEV_REGISTRY not in [f for f, _ in files]:
        return 0
    before = os.path.getsize(pak)
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="jukebox_pak_") as tmp:
        ext = os.path.join(tmp, "x")
        subprocess.run([unrealpak, pak, "-Extract", ext], capture_output=True, creationflags=no_window, check=True)
        resp = os.path.join(tmp, "files.txt")
        with open(resp, "w", encoding="utf-8") as f:
            for rel, comp in files:
                if rel == DEV_REGISTRY:
                    continue
                src = os.path.join(ext, *rel.split("/"))
                if not os.path.isfile(src):
                    raise RuntimeError("extracting the mod pak failed ({} missing)".format(rel))
                f.write('"{}" "{}{}"{}\n'.format(src, mount, rel, " -compress" if comp != "None" else ""))
        new_pak = os.path.join(tmp, os.path.basename(pak))
        subprocess.run([unrealpak, new_pak, "-create=" + resp, "-compressionformats=Zlib"],
                       capture_output=True, creationflags=no_window, check=True)
        new_mount, new_files = _pak_list(unrealpak, new_pak)
        expected = sorted(f for f, _ in files if f != DEV_REGISTRY)
        if new_mount != mount or sorted(f for f, _ in new_files) != expected:
            raise RuntimeError("the rebuilt mod pak didn't match the original layout")
        shutil.copyfile(new_pak, pak)
    return before - os.path.getsize(pak)


def assemble(mod, modkit_project_dir, work):
    """Build Output/<Mod>/Release/<Mod>. Returns its path."""
    ugc = published_ugc_files(modkit_project_dir, mod)
    if not ugc:
        raise RuntimeError("The mod hasn't been packaged yet. Use Package Mod > {} in the Mod Kit first.".format(mod))
    audio_dir = os.path.join(work, "AudioPak")
    audio = {e: os.path.join(audio_dir, "{}CrimeBossAudio.{}".format(mod, e)) for e in PAK_EXTS}
    if not all(os.path.isfile(p) for p in audio.values()):
        raise RuntimeError("The audio pak is missing. Run Jukebox > Build Jukebox Mod first.")
    release = os.path.join(work, "Release", mod)
    shutil.rmtree(release, ignore_errors=True)
    dst = os.path.join(release, PAKS_REL)
    os.makedirs(dst)
    for p in list(ugc.values()) + list(audio.values()):
        shutil.copy2(p, dst)
    # Drop the editor-only DevelopmentAssetRegistry.bin from the copied UGC pak (the
    # Mod Kit's own Publish folder is left untouched). Never fatal: keep the original on failure.
    unrealpak = _unrealpak(modkit_project_dir)
    if unrealpak:
        pak = os.path.join(dst, os.path.basename(ugc["pak"]))
        try:
            saved = strip_dev_registry(pak, unrealpak)
            if saved:
                print("  removed DevelopmentAssetRegistry.bin from the mod pak ({:.1f} MB smaller)".format(
                    saved / 1048576))
        except Exception as e:
            shutil.copy2(ugc["pak"], pak)
            print("  ! could not slim the mod pak, keeping it as packaged: {}".format(e))
    return release


def install(release, game_mods_dir):
    mod = os.path.basename(release)
    target = os.path.join(game_mods_dir, mod)
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(release, target)
    return target


def find_game_mods_dir():
    """Look for Crime Boss: Rockay City in the Steam libraries."""
    import re
    vdf = r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"
    libs = [r"C:\Program Files (x86)\Steam"]
    try:
        with open(vdf, encoding="utf-8") as f:
            libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s*"([^"]+)"', f.read())]
    except OSError:
        pass
    for lib in libs:
        d = os.path.join(lib, "steamapps", "common", "CrimeBossRockayCity", "CrimeBoss")
        if os.path.isdir(d):
            return os.path.join(d, "Mods")
    return None
