Put your music here, one folder per mod, one folder per song inside it:

  Songs\
    MyHeistMusic\                <- mod name (the folder name is used as the mod name)
      Steel Wrapped Gift\        <- song name (shown in the jukebox, can be changed in song.ini)
        stealth\
          01_stealth_loop.wav
        control\
          01_control_loop.wav
        assault\
          01_anticipation.wav    <- plays once...
          02_assault_loop.wav    <- ...then this loops forever
      Another Song\
        ...

ONE-SONG MOD
  Jukebox > Create Jukebox Mod makes Songs\<ModName>\ with empty stealth\, control\ and
  assault\ folders already in it - just drop the music in. The song then takes the mod's
  name; change display_name in its song.ini.
  For more songs, add one folder per song next to them instead (empty section folders are
  ignored, so you can leave or delete them).

RULES
  * Files in a section play in name order (01_, 02_, ... is easiest).
  * Any file with "loop" in its name loops forever. If no file has "loop" in its name,
    the last file in the section loops.
  * Instead of sub-folders you can put the files straight in the song folder and start
    their names with the section: stealth_loop.wav, assault_1_intro.wav, assault_2_loop.wav
  * Missing a section? It is filled in automatically (e.g. no control music -> assault plays).
  * WAV always works. MP3/OGG/FLAC/M4A also work if ffmpeg is installed.

EXTRA SECTIONS (optional, for more variety)
  The game has 3 stealth states and 2 assault states. If you add any of these folders they
  replace the normal section for that state only:
    stealth1  stealth2  stealth3  assault1  assault2  combat

SETTINGS
  The first build creates a song.ini in each song folder. Open it with Notepad to change
  the jukebox name, volume, transition style, tempo and compression quality.

LOUDNESS
  normalize = -14          make every part equally loud (needs ffmpeg); -14 is loud, -18 calmer.
                           Quiet parts go up, loud parts down, never past 0 dB peak.
  volume_db = 3            whole song louder/quieter (in dB)
  stealth_volume_db = 2    one part louder/quieter (also control_, assault_, stealth1_ ...)
