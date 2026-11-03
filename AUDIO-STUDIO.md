# Audio Studio handbook

Open Mod Creator > Audio Studio. The in-app Guide & shortcuts tab contains the same instructions.

## Start here

### Your first mod

1  Select the game copy in Merge and Deploy. Open Audio Studio from Mod Creator.
2  Choose a collection and a sound. Play original to hear the game audio.
3  Create an audio project, make a small change, then Play edited.
4  Open Finish & export. Include audio, visuals, or both; name the mod and export one ZIP.
5  Import that ZIP into your mod manager and enable it. In Laboratory, use Merge and Install All. In HellForge, press PLAY in its launcher.

### Know what is saved

Audio edits save automatically in the .audi project. Keep that project and its audio folder together. Visual replacements are staged until exported. A finished mod ZIP is the installable result; the project is for continuing your work.

## Replace and preview audio

### Find the right sound

Search collections, choose one, then search its sounds. The Edited filter shows your changed entries. Unavailable entries have no installed audio. A shared sound can be used by several weapons or events; changing it affects all those uses.

### Replace a clip

Create or open an audio project. Select a sound and choose Import replacement audio. WAV, MP3, FLAC, OGG and other supported audio are converted automatically. The input is copied into your project. Play original and Play edited compare the same selected sound. Stop ends playback.

### Trim, timing and names

More options contains trimming, mute, restore, timing and local display names. Enter Start and End in seconds, then Save trimmed copy. The input stays intact. Use the replacement’s length for most replacements; single-sound Apply volume saves this setting. A local display name helps recognition without changing the sound ID.

## Volume and multiple sounds

### Set a level

0 dB keeps the current source level; positive values boost it and negative values reduce it. The slider moves in half-dB steps; the number box allows a wider range. Apply volume saves the displayed value. Listen to Play edited before exporting: a large boost can clip or distort.

### Change a selection

Ctrl-click picks individual rows. Shift-click selects a range. With the sound list focused, Ctrl+A selects all visible rows. Apply volume sets the same absolute dB value on every selected sound, as one undo step. It does not add that value to each sound’s previous gain. Each replacement keeps its own timing. Deselect unavailable entries first.

### What the other buttons do

Bulk selection currently applies to volume only. Preview, replacement import, trim, mute, restore and rename use the first selected sound. That sound’s current gain fills the controls; choose your intended common value before applying to the selection. Undo and Redo work on saved audio edits.

## Visual assets and combined mods

### Use native resources

Open Visual assets and choose a source mod ZIP or a main native archive. Keep .stream and .gpu_resources sidecars beside a loose archive. Select the target resource, then choose a donor resource of the same type, or import a native asset bundle. PNG/JPG/DDS files need a texture-authoring conversion before native import.

### Change a gun’s look and sound

Stage the visual replacements in Visual assets. Make the audio edits in Audio studio. Then open Finish & export and include both current projects. You can also add previously finished patch ZIPs. The exporter combines resource patches into one manager-ready package and preserves the matching sidecars.

### Resolve overlaps

If two included sources change the same resource differently, export stops and tells you which ones overlap. Choose one version or resolve the overlap in the source project, then export again. The previous finished ZIP is preserved on failure.

## Finish, export and install

### One finished ZIP

Select Current audio project, Current visual replacements, or add completed patch ZIPs. Name the mod and add a description. Review the target game copy. Export finished mod ZIP creates the manager manifest, native patches and sidecars. Leave Add to Mod Library enabled for a direct handoff. Export itself never deploys the mod.

### Use it in a manager

Import the finished ZIP directly and enable it; audio and visual resource replacements do not need a separate loader. In Laboratory, review options and priority, then Merge and Install All. In HellForge, select its installation first, synchronize the packages and press PLAY there. Other managers must support the common HD2 cosmetic-pack manifest and native patch format.

### Build for the intended copy

Steam and HellForge can use different game builds. Use resources from the copy that will run the mod. Extra ZIPs use their default options. Export one chosen variant first when combining a multi-option pack. ZIP verification checks structure and resource bytes; test the result in gameplay before sharing it.

## HellForge and troubleshooting

### HellForge packages in the library

Import a native package as a ZIP, 7z, RAR or complete folder; a manifest file can select its folder too. Keep manifests, source code, DLLs, data specs, stats and Lua resources together. Laboratory preserves those contents and lets HellForge build and stage them. Required runtimes, matching SDK/game versions and native build errors are still checked by HellForge.

### A sound becomes silent

Confirm that Audio Studio and deployment use the same game copy. Preview the original and edited clip. Check that Mute is not staged and the entry is installed. Re-export against the target copy and test with conflicting audio mods disabled. The reported Stingray issue still needs in-game confirmation; a verified archive alone does not prove playback.

### An import or export fails

Keep source archives and their sidecars together. Choose a separate output location outside the game. A native asset bundle is for editing a resource; a finished mod ZIP is for installation. A Steam sealed-data mod cannot be made HellForge-native merely by putting it in a ZIP. Read the error and use a compatible native version.

## All shortcuts

| Shortcut | Action |
|---|---|
| F1 | Open this guide |
| Ctrl+N | Create an audio project |
| Ctrl+O | Open an audio project, or a visual source in the Visual assets tab |
| Ctrl+I | Import replacement audio for the first selected sound |
| Ctrl+F | Search sounds |
| Ctrl+Shift+F | Search collections |
| Ctrl+A | Select all visible sounds while the sound list has focus |
| Ctrl-click | Add or remove an individual sound from the selection |
| Shift-click | Select a range of sounds |
| Space | Play / stop while the sound list has focus |
| Escape | Stop playback |
| Ctrl+Z | Undo an audio edit |
| Ctrl+Y / Ctrl+Shift+Z | Redo an audio edit |
| Ctrl+E | Open Finish & export |
| Ctrl+W | Leave the studio when no operation is running |
| Mouse wheel | Scroll the Finish & export review; the export action stays visible |

Shortcuts are scoped to the studio. Text fields retain normal typing, selection and text-edit undo.
