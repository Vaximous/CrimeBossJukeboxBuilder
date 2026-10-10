"""Reads the Songs/<Mod>/<Song>/ folders and works out what goes where."""
import configparser
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".opus", ".wma"}

# Folder / filename-prefix keywords a song can use. Longest first so "stealth2" wins over "stealth".
SECTIONS = ["stealth1", "stealth2", "stealth3", "assault1", "assault2", "stealth", "control", "assault", "combat"]

# Which section plays for each game state (first one that exists wins).
STATE_MAP = {
    "State_Stealth1":           ["stealth1", "stealth", "control", "assault"],
    "State_Stealth2":           ["stealth2", "stealth", "control", "assault"],
    "State_Stealth3":           ["stealth3", "stealth", "control", "assault"],
    "State_BlackscreenStealth": ["stealth", "control", "assault"],
    "State_Control":            ["control", "assault", "stealth"],
    "State_BlackscreenControl": ["control", "assault", "stealth"],
    "State_Assault1":           ["assault1", "assault", "control", "stealth"],
    "State_Assault2":           ["assault2", "assault", "control", "stealth"],
    "State_BlackscreenAssault": ["assault", "control", "stealth"],
    "State_Combat":             ["combat", "assault", "control", "stealth"],
}

# Every state in the game's StateGrp_MissionState (names must match the game exactly).
ALL_MISSION_STATES = ["State_Assault1", "State_Assault2", "State_BlackscreenAssault", "State_BlackscreenControl",
                      "State_BlackscreenStealth", "State_Combat", "State_Control", "State_Cutscene",
                      "State_NoMusic", "State_Stealth1", "State_Stealth2", "State_Stealth3"]

TRANSITIONS = {"immediate": 0, "next_grid": 1, "next_bar": 2, "next_beat": 3, "next_cue": 4, "exit_cue": 7}

DEFAULT_SONG_INI = """\
; Settings for this song. Every line is optional - delete or change what you like.
[song]
; Name shown in the in-game jukebox
display_name = {display}

; Overall loudness change in decibels (e.g. 3 = louder, -3 = quieter)
volume_db = 0
{loudness}
; How the music switches when the heist changes phase (stealth -> assault, ...):
;   immediate  - cut straight away (works for everything)
;   next_beat / next_bar / next_grid - wait for the beat/bar (set tempo below!)
;   exit_cue   - wait for the current piece to finish
transition = immediate

; Short fade-out of the old part when switching, in milliseconds (0 = off)
fade_out_ms = 0

; Only matters for next_beat / next_bar / next_grid
tempo = 120
time_signature = 4/4

; Vorbis quality, -2 (smallest) to 10 (best). 7 sounds identical to the original for most people.
quality = 7
"""


LOUDNESS_INI = """
; Make every part equally loud: a target loudness in LUFS (-14 = loud/punchy, -18 = calmer),
; or off. Quiet parts are turned up and loud parts down, but a part is never pushed past
; 0 dB peak (no clipping). Needs ffmpeg.
normalize = off

; Extra loudness per part in decibels, applied on top of everything else
stealth_volume_db = 0
control_volume_db = 0
assault_volume_db = 0
"""

PEAK_CEILING_DBTP = -0.5   # normalize never raises a piece's true peak above this


@dataclass
class Piece:
    path: str          # WAV used for import
    name: str          # Wwise segment name
    loop: bool
    gain_db: float = 0.0   # from normalize


@dataclass
class Song:
    folder: str
    id: str                                  # safe identifier used for Wwise objects
    display_name: str
    sections: dict = field(default_factory=dict)  # section -> [Piece]
    volume_db: float = 0.0
    transition: str = "immediate"
    fade_out_ms: float = 0.0
    tempo: float = 120.0
    time_sig: tuple = (4, 4)
    quality: float = 7.0
    normalize: float = None                  # target LUFS, None = off
    section_volume: dict = field(default_factory=dict)  # section -> dB
    warnings: list = field(default_factory=list)

    @property
    def event_name(self):
        return f"Play_{self.id}"

    def state_targets(self):
        """state name -> section name, using fallbacks for missing sections."""
        out = {}
        for state, prefs in STATE_MAP.items():
            for sec in prefs:
                if sec in self.sections:
                    out[state] = sec
                    break
        return out


def safe_id(text):
    s = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_")
    if not s:
        s = "Song"
    if s[0].isdigit():
        s = "S_" + s
    return s


def _natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _section_of(name):
    low = name.lower()
    for sec in SECTIONS:
        if low == sec or re.match(rf"^{sec}(?![a-z0-9])", low) or re.match(rf"^{sec}[ _\-.]", low):
            return sec
    return None


def looks_like_song(folder):
    """True if the folder directly holds section folders with audio, or section-named audio files.
    Empty section folders (made by Create Jukebox Mod) don't count."""
    for entry in os.listdir(folder):
        full = os.path.join(folder, entry)
        if os.path.isdir(full) and _section_of(entry):
            if any(os.path.splitext(f)[1].lower() in AUDIO_EXTS for f in os.listdir(full)):
                return True
            continue
        if os.path.splitext(entry)[1].lower() in AUDIO_EXTS and _section_of(entry):
            return True
    return False


def _ensure_wav(src, convert_dir, ffmpeg):
    if src.lower().endswith(".wav"):
        return src
    if not ffmpeg:
        raise RuntimeError(f"'{os.path.basename(src)}' is not a WAV and ffmpeg was not found. "
                           "Convert it to WAV or install ffmpeg (see README).")
    os.makedirs(convert_dir, exist_ok=True)
    dst = os.path.join(convert_dir, os.path.splitext(os.path.basename(src))[0] + ".wav")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src, "-ar", "48000", "-c:a", "pcm_s16le", dst],
                       check=True)
    return dst


def load_song(folder, work_dir, ffmpeg=None):
    folder_name = os.path.basename(os.path.normpath(folder))
    ini_path = os.path.join(folder, "song.ini")
    if not os.path.exists(ini_path):
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_SONG_INI.format(display=folder_name, loudness=LOUDNESS_INI))
    else:
        with open(ini_path, encoding="utf-8") as f:
            existing = f.read()
        if "normalize" not in existing:   # song.ini from an older version: add the new options
            with open(ini_path, "a", encoding="utf-8") as f:
                f.write("\n" + LOUDNESS_INI)

    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cp.read(ini_path, encoding="utf-8")
    sec = cp["song"] if cp.has_section("song") else {}

    song = Song(folder=folder, id=safe_id(folder_name),
                display_name=sec.get("display_name", folder_name).strip() or folder_name)
    try:
        song.volume_db = float(sec.get("volume_db", 0))
        song.fade_out_ms = float(sec.get("fade_out_ms", 0))
        song.tempo = float(sec.get("tempo", 120))
        song.quality = max(-2.0, min(10.0, float(sec.get("quality", 7))))
        num, den = sec.get("time_signature", "4/4").split("/")
        song.time_sig = (int(num), int(den))
        norm = sec.get("normalize", "off").strip().lower()
        if norm not in ("", "off", "no", "false", "0"):
            song.normalize = float(norm.replace("lufs", ""))
            if song.normalize > 0:
                song.normalize = -song.normalize   # "14" means -14 LUFS
        for key in sec:
            if key.endswith("_volume_db") and key[:-len("_volume_db")] in SECTIONS:
                song.section_volume[key[:-len("_volume_db")]] = float(sec.get(key) or 0)
    except ValueError as e:
        raise RuntimeError(f"{ini_path}: {e}") from None
    song.transition = sec.get("transition", "immediate").strip().lower()
    if song.transition not in TRANSITIONS:
        raise RuntimeError(f"{ini_path}: transition must be one of {', '.join(TRANSITIONS)}")

    # Gather audio files: section sub-folders, or files named "<section>_whatever.wav" in the song folder.
    found = {}
    for entry in sorted(os.listdir(folder), key=_natural_key):
        full = os.path.join(folder, entry)
        if os.path.isdir(full):
            s = _section_of(entry)
            if not s:
                song.warnings.append(f"ignored folder '{entry}' (not a known section)")
                continue
            for f in sorted(os.listdir(full), key=_natural_key):
                if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                    found.setdefault(s, []).append(os.path.join(full, f))
        elif os.path.splitext(entry)[1].lower() in AUDIO_EXTS:
            s = _section_of(entry)
            if s:
                found.setdefault(s, []).append(full)
            else:
                song.warnings.append(f"ignored '{entry}' (name must start with stealth/control/assault/...)")

    if not found:
        raise RuntimeError(f"No audio found in '{folder}'. Put WAVs in stealth/, control/ and assault/ sub-folders.")

    convert_dir = os.path.join(work_dir, "_converted", song.id)
    for s, files in found.items():
        files.sort(key=lambda p: _natural_key(os.path.basename(p)))
        loops = [("loop" in os.path.basename(p).lower()) for p in files]
        if not any(loops):
            loops[-1] = True
        pieces = []
        for p, lp in zip(files, loops):
            stem = re.sub(r"[^A-Za-z0-9_]+", "_", os.path.splitext(os.path.basename(p))[0]).strip("_")
            pieces.append(Piece(path=_ensure_wav(p, convert_dir, ffmpeg), name=f"{song.id}_{s}_{stem}", loop=lp))
        first_loop = loops.index(True)
        if first_loop < len(files) - 1:
            skipped = ", ".join(os.path.basename(p) for p in files[first_loop + 1:])
            song.warnings.append(f"{s}: '{os.path.basename(files[first_loop])}' loops forever, "
                                 f"so these will never play: {skipped}")
        song.sections[s] = pieces

    if song.normalize is not None:
        if not ffmpeg:
            song.warnings.append("normalize needs ffmpeg - skipped")
        else:
            cache_path = os.path.join(work_dir, "_loudness.json")
            for s, pieces in song.sections.items():
                for p in pieces:
                    lufs, peak = measure_loudness(p.path, ffmpeg, cache_path)
                    if lufs is None:
                        song.warnings.append(f"could not measure {os.path.basename(p.path)} (silent?)")
                        continue
                    p.gain_db = round(min(song.normalize - lufs, PEAK_CEILING_DBTP - peak), 1)
                    note = " (limited by its peak)" if PEAK_CEILING_DBTP - peak < song.normalize - lufs else ""
                    song.warnings.append(f"normalize {s}/{os.path.basename(p.path)}: {lufs:.1f} LUFS -> "
                                         f"{p.gain_db:+.1f} dB{note}")

    for base in ("stealth", "control", "assault"):
        if base not in song.sections:
            used = song.state_targets().get({"stealth": "State_BlackscreenStealth", "control": "State_Control",
                                             "assault": "State_BlackscreenAssault"}[base])
            song.warnings.append(f"no '{base}' music - using '{used}' instead")
    return song


def measure_loudness(path, ffmpeg, cache_path):
    """Integrated loudness (LUFS) and true peak (dBTP) via ffmpeg's EBU R128 filter, cached."""
    import json
    key = "{}|{}|{}".format(os.path.abspath(path), os.path.getmtime(path), os.path.getsize(path))
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    if key in cache:
        return tuple(cache[key])
    res = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    summary = res.stderr.rsplit("Summary:", 1)[-1]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    pk = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not i or not pk or "inf" in i.group(1):
        return None, None
    val = (float(i.group(1)), float(pk.group(1)) if "inf" not in pk.group(1) else -100.0)
    cache[key] = val
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1)
    return val


def find_ffmpeg(configured=None):
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("ffmpeg")
