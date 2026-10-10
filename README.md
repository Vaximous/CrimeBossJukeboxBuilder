# Crime Boss Jukebox Builder

This tool automates the community guide *"Crime Boss Custom Tracks for the Wwise"*. You put your
music in folders, and it builds the Wwise project for you. You don't have to open the Wwise editor.

> **Status:** the whole guide is automated (Wwise, Part A, Part B, Part C), all from a
> **Jukebox** menu inside the Crime Boss Mod Kit editor. You don't need stock UE 4.27 or Visual
> Studio, because the audio pak is built with the Mod Kit's own engine and Wwise plugin.

## Making a jukebox mod (in the Crime Boss Mod Kit)

1. **Jukebox → Create Jukebox Mod...** (once per mod; the editor restarts once).
2. **Jukebox → Open Songs Folder...** and drop your music in (see `Songs\README.txt`).
3. **Jukebox → Build Jukebox Mod...** A console window shows progress (a few minutes).
   You can keep working in the editor. It:
   * builds the Wwise project (states, loops, Vorbis...);
   * builds the audio pak headlessly on the Mod Kit engine: imports the sound data, creates
     `PDA_<Song>` in `/Game/JukeboxMod/Tracks/<Mod>/`, cooks `pakchunk999`, renames it
     `<Mod>CrimeBossAudio` and runs `set_container_id` on it;
   * fills `DT_<Mod>` with the songs.
4. When it says it's done, use the Mod Kit's normal **Package Mod → <Mod>**.
5. Jukebox Builder notices the new package, puts the final mod together in
   `Output\<Mod>\Release\<Mod>\`, and offers to **install it into the game's `CrimeBoss\Mods`**.

If you package later, or after restarting the editor, it still notices. You can also run
**Jukebox → Install into Game** yourself. Logs are in `Output\<Mod>\logs`
(**Jukebox → Open Build Folder...**).

The finished mod uses the same layout as working jukebox mods:
```
<Mod>\Content\Paks\WindowsNoEditor\<Mod>CrimeBoss-WindowsNoEditor.pak/.ucas/.utoc   (Package Mod)
<Mod>\Content\Paks\WindowsNoEditor\<Mod>CrimeBossAudio.pak/.ucas/.utoc             (audio)
```
Players also need **JukeboxMod** installed.

The Mod Kit's Package Mod adds an editor-only debug file (`Metadata/DevelopmentAssetRegistry.bin`,
about 20 MB) to every mod pak. The final jukebox mod is built without it, so the UGC pak is a few KB.
Your Mod Kit's own `Publish` folder is left untouched.

Why does Create need a restart? The built-in Create Mod dialog's template list is compiled
into 505's plugin, and editor Python can't load a newly created mod without a restart. The
editor asks you to save first, then reopens by itself. Why press Package Mod yourself?
505's packager is part of their compiled plugin, and Python can't press its button.

Why the restart? The built-in Create Mod dialog's template list is compiled into 505's
plugin, so new templates can't be added to it, and editor Python can't load a newly
created mod without a restart. The editor asks you to save first, then reopens by itself.

Setup also does two one-time things from the guide for you: it copies the `JukeboxMod`
plugin into `Mods\`, and it adds `/JukeboxMod` and `/Game/JukeboxMod` to
*Directories to never cook*.

## What you need

| | |
|---|---|
| **Crime Boss Mod Kit** | The official one from the Epic Games Store, opened at least once. |
| **Wwise 2021.1.14** (or 2021.1.13) | Install it with the Audiokinetic Launcher. Authoring is all you need. |
| **Python 3.9+** | Only for `Setup.bat`: <https://www.python.org/downloads/>. Tick *"Add python.exe to PATH"*. The editor menu uses the Mod Kit's own Python. |
| ffmpeg *(optional)* | For MP3/OGG/FLAC/M4A files and `normalize` in `song.ini`. `winget install ffmpeg` |

You do **not** need stock Unreal Engine 4.27 or Visual Studio.

## First-time setup

1. Unzip this folder somewhere permanent, e.g. `C:\CBModKit\JukeboxBuilder` (the Mod Kit
   plugin remembers where it is).
2. Close the Mod Kit editor and double-click **`Setup.bat`**. It:
   * finds Wwise, ffmpeg, the Mod Kit and your game's `Mods` folder (and asks for the Mod
     Kit's `CrimeBoss.uproject` if it can't find it);
   * downloads the guide's template projects and `set_container_id.exe` into `ThirdParty\`;
   * installs the **Jukebox** menu plugin and `JukeboxMod` into the Mod Kit.
3. Open the Mod Kit. You should see a **Jukebox** menu, and a **Jukebox** button on the toolbar.

Run `Setup.bat` again whenever you move this folder or update the tool.

## Wwise only (advanced)

`BuildWwise.bat` builds just the Wwise projects for every mod in `Songs\` (or for a folder
you drag onto it), into `Output\<Mod>\<Mod>_Wwise\`. That's useful if you want to package
by hand following the guide.

## What it does for you (compared with the guide)

| Guide step | Automatic |
|---|---|
| New Wwise project | ✅ |
| `Music_FPS` bus at -13 dB | ✅ |
| `WU_GameState` / `StateGrp_MissionState` with every state | ✅ |
| Music Switch Container with stealth / control / assault playlists | ✅ (one per song) |
| Output bus set to `Music_FPS` | ✅ |
| Transition set to Immediate / Next beat | ✅ (`transition` in `song.ini`) |
| State Group association paths (Association Editor) | ✅ |
| Import WAVs as music segments | ✅ |
| Playlist order with infinite loops | ✅ (files whose name contains "loop") |
| Vorbis conversion, quality 7, high-quality resampling | ✅ (`quality` in `song.ini`) |
| Event with a Play action | ✅ (`Play_<SongName>`) |
| Checks that the project builds | ✅ (a test SoundBank is generated) |

### Which music plays when

| Game state | Section used (first one that exists) |
|---|---|
| Stealth1 / 2 / 3 | stealth1/2/3 → stealth → control → assault |
| BlackscreenStealth | stealth → control → assault |
| Control, BlackscreenControl | control → assault → stealth |
| Assault1 / 2 | assault1/2 → assault → control → stealth |
| BlackscreenAssault | assault → control → stealth |
| Combat | combat → assault → control → stealth |
| Cutscene, NoMusic | nothing (as in the guide) |

## Tweaking by hand

You can open the generated `.wproj` in Wwise to fine-tune trims, tempo and so on. **But
building again (from the menu or `BuildWwise.bat`) replaces each song's container**, so either make your
changes in `song.ini` or stop rebuilding once you start editing by hand.

## Folder layout

```
JukeboxBuilder\
  Setup.bat, BuildWwise.bat   double-click these
  Songs\                      your music (input)
  Output\                     generated projects (safe to delete)
  ThirdParty\                 downloaded by Setup.bat (templates, set_container_id.exe)
  EditorPlugin\               the Jukebox menu plugin Setup.bat copies into the Mod Kit
  jukebox_builder\            the Python code (no extra packages needed)
  config.ini                  tool paths (made by Setup.bat)
```

## Troubleshooting

* **"WwiseConsole.exe not found"**: put the full path in `config.ini`, e.g.
  `wwise_console = C:\Audiokinetic\Wwise2021.1.14.8108\Authoring\x64\Release\bin\WwiseConsole.exe`
* **Build hangs or fails right after "starting Wwise"**: close the Wwise editor if it has the
  same project open. Details are in `Output\<Mod>\wwise_server.log`.
* **"Wwise reported a problem"**: see `Output\<Mod>\wwise_check.log`.
* **The audio pak step failed**: the logs are in `Output\<Mod>\logs\`
  (`1_sound_data`, `2_track_assets`, `3_package`). Use **Jukebox → Open Build Folder**.
* **No Jukebox menu**: check the editor's Output Log for "Jukebox Builder", and run
  `Setup.bat` again.
* **Install into the game fails**: close the game first, since it locks the files.
* **Music too quiet or uneven**: set `normalize = -14` in the song's `song.ini` (see
  `Songs\README.txt`).

## Credits

* The original guide *"Crime Boss Custom Tracks for the Wwise"* and its template projects are by
  its author ("the number"). `JukeboxMod` is by braidy08. `Setup.bat` downloads these from
  the guide's original links; they aren't included in this download.
* [`set_container_id`](https://github.com/rtkzboss/set-container-id) is by rtkzboss.
