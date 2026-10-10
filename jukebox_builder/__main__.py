import argparse
import json
import os
import sys
import traceback

from . import config


def cmd_wwise(args):
    from .songs import find_ffmpeg, looks_like_song
    from .waapi import find_wwise_console
    from .wwise import build_mod

    paths = config.load()["paths"]
    wc = find_wwise_console(paths.get("wwise_console"))
    if not wc:
        print("WwiseConsole.exe not found - run Setup.bat first.")
        return 1
    ffmpeg = find_ffmpeg(paths.get("ffmpeg"))

    mods = args.mods or [os.path.join(config.SONGS_DIR, d) for d in sorted(os.listdir(config.SONGS_DIR))
                         if os.path.isdir(os.path.join(config.SONGS_DIR, d)) and not d.startswith(("_", "."))]
    if not mods:
        print(f"No mod folders in {config.SONGS_DIR}. See Songs\\README.txt.")
        return 1
    failed = 0
    for m in mods:
        m = os.path.abspath(m)
        # A folder directly in Songs\ is always a mod (it may hold one song directly).
        # Anywhere deeper, dropping a song folder builds its parent mod.
        if os.path.normcase(os.path.dirname(m)) != os.path.normcase(os.path.abspath(config.SONGS_DIR)) \
                and looks_like_song(m):
            m = os.path.dirname(m)
        try:
            build_mod(m, config.OUTPUT_DIR, wc, ffmpeg)
        except Exception as e:  # report and carry on with the next mod
            failed += 1
            print(f"\n  FAILED: {e}")
            if args.debug:
                traceback.print_exc()
        print()
    return 1 if failed else 0


def _write_status(work, **status):
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "build_status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def cmd_build(args):
    """Wwise project + audio pak for one mod (everything before the Mod Kit's Package Mod)."""
    from .audio import Engine, build_audio_pak
    from .songs import find_ffmpeg
    from .waapi import find_wwise_console
    from .wwise import build_mod

    mod_dir = os.path.abspath(args.mod)
    mod = os.path.basename(mod_dir)
    work = os.path.join(config.OUTPUT_DIR, mod)
    _write_status(work, state="running", mod=mod)
    try:
        paths = config.load()["paths"]
        wc = find_wwise_console(paths.get("wwise_console"))
        if not wc:
            raise RuntimeError("WwiseConsole.exe not found - run Setup.bat first.")
        modkit = args.modkit or paths.get("modkit_project")
        if not modkit or not os.path.isfile(modkit):
            raise RuntimeError("The Mod Kit project wasn't found - run Setup.bat first.")
        sid = os.path.join(config.THIRD_PARTY_DIR, "set_container_id.exe")
        if not os.path.isfile(sid):
            raise RuntimeError("set_container_id.exe is missing - run Setup.bat again.")
        engine = Engine(modkit)
        wwise_root = os.path.normpath(os.path.join(os.path.dirname(wc), "..", "..", "..", ".."))

        print("[1/2] Wwise")
        wproj, songs = build_mod(mod_dir, config.OUTPUT_DIR, wc, find_ffmpeg(paths.get("ffmpeg")))
        print("\n[2/2] Audio pak (Unreal, headless)")
        build_audio_pak(mod, work, wproj, songs, engine, wwise_root, sid)
    except Exception as e:
        _write_status(work, state="failed", mod=mod, message=str(e))
        print("\nFAILED: {}".format(e))
        if args.debug:
            traceback.print_exc()
        return 1
    _write_status(work, state="done", mod=mod, songs=[s.display_name for s in songs])
    print("\nDONE - back in the Mod Kit, package the mod (Package Mod > {}).".format(mod))
    return 0


def main():
    p = argparse.ArgumentParser(prog="jukebox_builder", description="Crime Boss jukebox mod builder")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True
    sub.add_parser("setup", help="find tools and download templates")
    w = sub.add_parser("wwise", help="build the Wwise project(s) from Songs/<Mod>/<Song>/")
    w.add_argument("mods", nargs="*", help="mod folders (default: every folder in Songs/)")
    w.add_argument("--debug", action="store_true")
    b = sub.add_parser("build", help="Wwise project + audio pak for one mod")
    b.add_argument("mod", help="Songs/<Mod> folder")
    b.add_argument("--modkit", help="path to the Mod Kit's CrimeBoss.uproject")
    b.add_argument("--debug", action="store_true")
    args = p.parse_args()

    if args.cmd == "setup":
        from .setup_tool import run
        return run()
    if args.cmd == "build":
        return cmd_build(args)
    return cmd_wwise(args)


if __name__ == "__main__":
    sys.exit(main())
