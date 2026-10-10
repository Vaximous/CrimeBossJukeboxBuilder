import configparser
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.ini")
SONGS_DIR = os.path.join(ROOT, "Songs")
OUTPUT_DIR = os.path.join(ROOT, "Output")
THIRD_PARTY_DIR = os.path.join(ROOT, "ThirdParty")

DEFAULTS = {
    "wwise_console": "",
    "ffmpeg": "",
    "modkit_project": "",
    "game_mods_dir": "",
}


def load():
    cp = configparser.ConfigParser()
    cp["paths"] = DEFAULTS
    if os.path.exists(CONFIG_PATH):
        cp.read(CONFIG_PATH, encoding="utf-8")
    return cp


def save(cp):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("; Jukebox Builder settings. Run Setup.bat to fill these in automatically.\n")
        cp.write(f)
