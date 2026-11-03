# Using ModDiver Laboratory with HellForge

Select the HellForge installation in **Merge and Deploy**. The root, `game`, `game/data` and `game/data/game` folder choices resolve to the same game copy. Audio Studio follows this selection automatically. A Steam capture or Steam file verification is not required for HellForge deployment; repair the copy through HellForge's own Settings when necessary.

## Create, import and play

1. Audio: open Audio Studio. Ctrl-click or Shift-click for multiple volume edits. Export against the HellForge copy, then add the ZIP to Mod Library.
   **Finish & export** can combine current audio and visual replacements, or completed patch ZIPs, into one manager-ready cosmetic pack. **Guide & shortcuts** (F1) contains the expanded handbook and every studio shortcut. Ctrl+E opens the finishing step.
2. Gameplay: choose **Open HellForge Stats Editor** in Mod Creator. The Nexus build does not bundle ModDiverEditor or SHODAN. Import an existing `hellforge-stats.json`, or choose **Read F8 changes** to copy the in-game editor's saved changes into the workspace. This reads Local Stats without changing it.
3. Search changes, select a row, adjust its value and click **Add / update stat**. Category and target suggestions come from imported data. New edits need HellForge's exact target and field names; the workspace gives a simple weapon example.
4. Give the mod a name and choose **Export + add to library**. HellForge's own checker must accept the file before the ZIP is saved. A failed check preserves any previous export. This checks stat names and values; the engine checks runtime layouts when the game loads.
5. Use **Merge and Install All** to synchronize selected library packages, options and priority. Then **Launch Game** opens HellForge: press **PLAY** there.

HellForge applies Local Stats after packaged mods. Reset conflicting edits in its F8 editor when testing a packaged change. Co-op players must follow HellForge's mod matching requirements. Adding a checked mod to the library does not deploy it automatically.

## Feature coverage

| Area | HellForge behavior |
|---|---|
| Audio and bulk volume | Reads the selected copy; exports verified patches; playback testing is still needed. |
| Gameplay and stat editing | Dedicated named-stat workflow across HellForge's supported categories, rather than Steam sealed-file exports. |
| Existing native and Lua packages | Full packages are passed through; HellForge builds/stages them and checks dependencies. |
| Visual assets | Native resource editing and patch export remain available; donor resources must match the target game build. |
| Library, options, priority and backup/import | Supported. Top library priority is translated to HellForge's top-first order. |
| Native package import | ZIP, 7z, RAR, complete folders and manifest-file selection. Code, source, stats, specs and Lua contents stay together for HellForge to build/load. |
| Older Windows HellForge | Uses its documented mods folder/state if mod-management commands are unavailable; only Laboratory-owned ZIPs can be replaced/removed. Close game/session before changes. |
| Data Bot | Checks native stats and builds data specs against the copy in temporary storage. Does not automatically port arbitrary Steam binary mods. |
| Purge | Removes only packages installed through Laboratory; preserves independently installed and bundled mods. |
| Steam-only built-in tweaks | Disabled. Use HellForge's bundled fixes or compatible native mods. |
| Game repair and verification | Managed by HellForge. Steam maintenance is not applied to its copy. |

Sealed generated-data mods, Steam editor presets and incompatible code DLLs cannot be converted by changing their packaging. There is no blanket guarantee for every imported mod, engine build or gameplay context. Current Linux HellForge uses its CLI through Proton; the legacy filesystem bridge is Windows-only and Linux execution has not been tested here.

## Formats and interface references

- [HellForge external launcher interface](https://github.com/SkyeShade/HellForge/blob/main/docs/external-launchers.md)
- [Named stats format](https://github.com/SkyeShade/HellForge/blob/main/docs/modding/stats-mods.md)
- The installed HellForge SDK's `docs/mods.md` documents the older mods-folder and settings format used by the Windows bridge.
