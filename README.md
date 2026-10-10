# Jukebox Builder

This tool automates the creation of jukebox mods, that shit was time consuming as fuck.

## Making a jukey

1. **Jukebox → Create Jukebox Mod...** (This shit will restart the editor).
2. **Jukebox → Open Songs Folder...**.
3. **Jukebox → Build Jukebox Mod...**.
   You can keep working in the editor. It:
   * builds the Wwise project (states, loops, Vorbis...);
   * builds the audio pak, imports the sound data, creates
     `PDA_<Song>` in `/Game/JukeboxMod/Tracks/<Mod>/`, cooks `pakchunk999`, renames it
     `<Mod>CrimeBossAudio` and runs `set_container_id` on it;
   * fills `DT_<Mod>` with the songs.
4. When it says it's done just package the mod as usual**.
5. Jukebox Builder notices the new package, puts the final mod in
   `Output\<Mod>\Release\<Mod>\`, and offers to **install it into the game's `CrimeBoss\Mods`**.


The finished mod uses the same layout as the other jukebox mods:
```
<Mod>\Content\Paks\WindowsNoEditor\<Mod>CrimeBoss-WindowsNoEditor.pak/.ucas/.utoc   (Package Mod)
<Mod>\Content\Paks\WindowsNoEditor\<Mod>CrimeBossAudio.pak/.ucas/.utoc             (audio)
```

## Requirements

| | |
|---|---|
| **Crime Boss Mod Kit** | [The official one from the Epic Games Store, opened at least once.](https://store.epicgames.com/p/crime-boss--modkit) |
| **Wwise 2021.1.14** (or 2021.1.13) | Install it with the Audiokinetic Launcher. Authoring is all you need. |
| **Python 3.9+** | Only for `Setup.bat`: <https://www.python.org/downloads/>. When installing make sure you click *"Add python.exe to PATH"*.|
| ffmpeg *(optional)* | For MP3/OGG/FLAC/M4A files and `normalize` in `song.ini`. `winget install ffmpeg` |

## Setup

1. Unzip this folder somewhere permanent, e.g. `C:\CBModKit\JukeboxBuilder` (the Mod Kit
   plugin remembers where it is).
2. double-click **`Setup.bat`**. Make sure the editor is closed if it's opened what it'll do is:
   * find Wwise, ffmpeg, the modkit and your mods folder;
   * downloads the guide's template projects and `set_container_id.exe` into `ThirdParty\`;
   * installs the **Jukebox** menu plugin and `JukeboxMod` into the modkit.
3. After it's all finished go ahead and open the modkit and you should see the new jukebox tab.

Run `Setup.bat` again whenever you move this folder or update the tool.

## Wwise only (advanced)

`BuildWwise.bat` builds just the Wwise projects for every mod in `Songs\` (or for a folder
you drag onto it), into `Output\<Mod>\<Mod>_Wwise\`. That's useful if you want to package
by hand following the guide.

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

