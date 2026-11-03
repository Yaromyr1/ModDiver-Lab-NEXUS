# ModDiver Laboratory 2.4.2

On Windows, extract the full Windows ZIP and double-click **ModDiver Laboratory.exe**. Python is included. Keep your existing App Data folder when updating.

On Linux, extract the Linux ZIP and follow **README-Linux.md**.

See **INSTALLATION.md** in the full platform download for the OS list and numbered installation guides.

[License](LICENSE) · [Licensing scope](LICENSING.md) · [Code signing policy](CODE-SIGNING-POLICY.md)

## START HERE — YOUR FIRST MOD

ModDiver Laboratory is a free, open-source mod manager and editing toolkit for Helldivers 2. You can use downloaded mods without knowing how to program. Start with Mod Library and Merge and Deploy; the editing tools are optional.

1. Close Helldivers 2. In Merge and Deploy, choose the Helldivers 2 installation folder — the folder containing data and bin, not the data folder itself. In Steam you can find it under the game’s Properties → Installed Files → Browse.

2. Start with clean game files. If another manager or editor has changed the game, restore its changes first or use Steam’s file verification. Click Capture Clean Game Files to save a stock snapshot. “Stock” means the original data used to compare and merge mods; it is not a backup of your whole game.

3. In Mod Library, use Add ZIP / 7Z or Add Folder. You normally do not need to unpack a ZIP first. The app keeps a managed copy of imported mod sources so moving the original download will not break the library.

4. Select the mod and review Options if it has optional parts. Included means that component will be used in the next installation. It does not mean the mod is already installed. Excluded components will be left out.

5. In Merge and Deploy, click Preview Deployment first. It checks selected mods, options, conflicts and target files without changing the game. It also checks for a program update silently in the background; an available update is offered after the preview finishes, never during it. Review whole-file fallbacks and errors. When ready, click MERGE and INSTALL ALL; the app stages outputs and recovery data before applying them.

6. Use START GAME to open Helldivers 2 through Steam. To undo changes managed by this app, close the game and click Purge All Mods.

## MOD LIBRARY — ORDER, OPTIONS AND TOGGLES

Click a card to select it; its outline highlights. Drag the name or preview to reorder or move into Loaders, Gameplay, or Visual & Audio, including an empty category. A drop marker shows where it will land, and the list scrolls near its edges. Up/Down buttons are no longer needed. The loader toggle next to Purge chooses whether the Loaders category deploys first (yellow) or last (grey). Click the loader button to change order. Higher cards win within each group.

Within a category, higher mods have priority when the same data value is changed. Categories organize the library; they do not make two conflicting mods compatible. Chef Shared Loader is an exception: its boot files have final priority. Preview and deployment logs identify the target, record or byte range where available, both mods, the winning priority, and any whole-file fallback.

Options controls the optional components declared by a mod. Included components use your theme accent; Excluded components are left out. Options save automatically. Use Merge and Install All to apply the selection.

Turning a mod ON stages it for the next installation. Turning an installed mod OFF restores the managed deployment and rebuilds the remaining previously deployed, enabled mods. It does not install newly enabled mods as a side effect. Wait for that operation to finish.

Each card’s red trash icon removes that library entry and keeps its source files. It does not by itself restore game files. Purge All Mods restores the managed game deployment while keeping your library. Completely Purge Mod Library deletes managed mod sources and library entries; it is separate from restoring game files.

A missing-source label means the stored mod source could not be found. Reimport the mod. The preview uses an image supplied by the mod when supported, otherwise the dark ModDiver Laboratory image.

## SETTINGS, LANGUAGE, SHORTCUTS AND GET MODS

Settings, marked with a gear in the sidebar, contains all theme presets, accent swatches, custom colours and separate interface/log font size controls. Logs default to 12 points; adjust Log font size in the theme section. The page scrolls when your window is small. Startup installation, imports, exports and removal operations show a blue loading bar with a white outline on your chosen theme background.

Choose English or Chinese (Simplified) in Language. The choice is saved immediately and the app automatically restarts to apply it. Settings also includes RESTART THE APP. Chinese covers the main interface, editor controls and an in-app user guide. Imported mod names, file paths, game identifiers and technical diagnostic logs retain their original text.

GENERATE NEW DESKTOP SHORTCUT creates a shortcut even if the first-run shortcut already exists. On Windows, launch with the EXE first so the shortcut points to the correct launcher and uses its yellow icon. On Linux, start with run-linux.sh; the desktop entry launches the update-aware bootstrap. Your desktop may ask you to allow launching that entry.

Get Mods in Mod Library opens a choice of Nexus Mods (orange), AyakaMods (dark cyan) and HellForge (red), with white text. Choose a site to open it in your default browser. Download your chosen mod, then import its ZIP/7Z or folder into the library.

## UPDATING THE APP, CHEF AND EDITORS

App updates: use Check for Updates below. Windows and Linux check for a newer stable release every time the app starts. Nothing is installed without your agreement. You can turn startup checks off below and still check manually.

The app downloads a small application package, shows download and installation progress, verifies it, and keeps the previous version for recovery. Your mod library, settings, stock snapshots and deployment backups live outside the versioned application files. Restart when prompted, or choose to restart later.

Windows: start from ModDiver Laboratory.exe to use in-app installation. This release uses launcher API 3: download and extract the full Windows ZIP once to enable the ModDiver Lab process name and original yellow icon in Task Manager. The normal updater replaces application files, not the launcher or its Python runtime. Keep your App Data folder. Do not run files out of the ZIP preview.

Linux: this release uses launcher API 3. Users of older Linux packages should download and extract the full Linux ZIP once, then launch with run-linux.sh. Later application updates install through Check for Updates. Starting source/yao_forge.py directly bypasses that launcher; the app then directs you to the release downloads.

Chef and SHODAN have their own update buttons in Tools. Updating the app does not imply that you downloaded the latest external tools. Check Chef for Updates installs a new loader package into the library; Merge and Install All applies it to the game. Keep only one Chef version enabled.

Custom tools: click Add Custom Tool 1, enter a name and confirm. Up to three names are saved; Add another tool appears while slots remain. Connect an executable, script or shortcut to launch it, or connect a ZIP, 7z or extracted loader folder to add it to the library. Removing a shortcut keeps its original file.

Lab Storage: check unused packages and choose Delete selected to permanently remove them. References in saved presets are also removed after confirmation.

Chef loader imports replace previous managed versions and update saved presets. SHODAN updates replace the active imported editor. Successful Data Bot updates remove superseded built-in mod caches.

Check SHODAN for Updates downloads the external Windows editor. IMPORT CHEF UPDATE MANUALLY remains available for manual Chef updates, including renamed download folders. SHODAN is Windows-only. ModDiverEditor supports Windows and Linux through 64-bit Wine. Its updates ship with Laboratory; there is no separate editor update import.

If checking fails, confirm your connection and try again later. GitHub can temporarily limit requests. A failed download or validation does not activate the new version. Release Downloads opens the official project page for manual installation. The app never requires an account or a paid subscription.

## LINUX — INSTALLATION AND EVERYDAY USE

ModDiverEditor: the Tools card opens the bundled editor on Windows and x86-64 Linux. Capture a clean stock baseline in Settings first. Saved editor settings remain editable; changes automatically update one linked Mod Library entry through a separate background worker. Update library saves all settings and waits for a verified library import, then closes the editor and returns Laboratory to Mod Library. A failed build keeps the editor open and preserves the previous mod. How to remove opens a themed instructions popup on every click. The editor does not install or restore game files. The library entry preserves its enabled state, category and priority; Changes pending deployment marks new output. Use Preview Deployment to review conflicts and whole-file fallbacks, then Merge and Install All to apply the enabled library. To remove editor changes, disable its library entry and deploy again. Failed builds keep the previous mod. After a game update or stock replacement, reopen the editor against fresh clean stock. Existing changes installed by older editor versions are not automatically removed; restore those with the old editor or Steam verification before capturing fresh stock. Linux requires a working 64-bit Wine installation and Python; wine and wine64 are both detected. Set MODDIVER_WINE to a custom Wine executable if needed. On immutable desktops, install Wine inside a writable Distrobox and launch ModDiver Laboratory there with access to the Steam library. The editor uses its own Wine prefix and the game folder selected in the app. ARM Linux and individual distro configurations have not been validated.

Extract the Linux ZIP and open Install ModDiver.desktop. If your desktop asks, mark it executable and choose Allow Launching or Run in Terminal. The installer installs dependencies on Ubuntu/Debian, Fedora, Arch, openSUSE and Alpine, copies the app into your user data folder, adds ModDiver Laboratory to the application menu and starts it. Your administrator password may be requested for system packages. The app itself runs as your normal user. You do not need Wine for the main app or native editor.

Linux desktop targets: Ubuntu, Debian, Linux Mint, Pop!_OS, Zorin OS and PikaOS use the Debian installer path; Fedora and compatible desktops use DNF; Arch, EndeavourOS, Manjaro, CachyOS and Garuda use Pacman; openSUSE uses Zypper (including bsdtar); Alpine uses APK with python3-tkinter from its community repository. A configured desktop session is required. Python 3.10 or newer is required. Run sh install-linux.sh --check to check dependencies without installing anything, or --print-dependencies to see the package list. These are installer targets, not a claim that every distribution has been tested.

SteamOS / Steam Deck (Desktop Mode), Bazzite, Aurora, Bluefin, Fedora Atomic, openSUSE Aeon and Kalpa desktops: run sh install-linux-distrobox.sh from the extracted Linux folder. This requires Distrobox and a working Podman or Docker runtime. The helper creates a user container named moddiver-laboratory using Ubuntu 24.04, installs dependencies inside it and adds an application-menu shortcut that re-enters the container. Keep the extracted folder in your home directory while installing. Game files and app data must be accessible from the container. If Distrobox is absent, follow your OS documentation first; the helper does not unlock or modify the host system image. This container path still needs real-device validation.

Distrobox references: https://distrobox.it/ ; Bazzite installation guidance: https://docs.bazzite.gg/Installing_and_Managing_Software/ ; SteamOS desktop guidance: https://help.steampowered.com/en/faqs/view/671A-4453-E8D2-323C . macOS and ChromeOS are not currently supported releases. SHODAN remains Windows-only. ModDiverEditor runs on Linux through 64-bit Wine, including inside a writable Distrobox on immutable distributions.

On Ubuntu or Debian, install the required packages with:
sudo apt update
sudo apt install python3 python3-tk libsodium23 luajit libarchive-tools xdg-utils
On other distributions install their equivalents: Python 3.10+, Tkinter, libsodium, LuaJIT 2.1 and xdg-open. bsdtar/libarchive enables 7z imports; ZIP imports work without it.

If your desktop blocks the installer shortcut, open a terminal in the extracted folder and run sh install-linux.sh. After installation, launch ModDiver Laboratory from your application menu. Portable launch is also available with:
sh run-linux.sh
Run it as your normal user. It needs write permission to your own Helldivers 2 installation, but should not be started with sudo. The script checks essential dependencies and explains missing ones.

Helldivers 2 runs through Steam/Proton. If the app does not find it, use Browse in Merge and Deploy. A common location is ~/.local/share/Steam/steamapps/common/Helldivers 2, but another Steam library or Flatpak Steam can use a different path. Steam’s Browse button is the reliable way to locate your installation.

Your files normally live in ~/.local/share/ModDiverLab, or $XDG_DATA_HOME/ModDiverLab if you set that location. Open App Data below opens the actual folder. Keep it when replacing the downloaded app folder. Versioned application files are in its app subfolder; launcher-linux.log records launch problems.

If the app cannot open a folder or start the game, check that xdg-open and Steam’s steam:// URL handler work on your desktop. If an update immediately crashes, the launcher attempts to return to the previous working version. For missing system packages, fix the dependency problem and run the script again.

Linux packages are built from the same Python sources. Automated launcher tests run during development, but a Windows build environment cannot establish that every Linux desktop, Proton setup or game mod works. If reporting a problem, include your distribution, app version, exact action and relevant log lines.

## GAME UPDATES, STOCK AND RECOVERY

Before a game update when possible, close the game and purge active mods. After the update, verify game files through Steam, launch and exit once, then capture fresh clean stock. Do not capture a modded game as clean stock. Mods and editing schemas may also need updates when the game changes.

Purge restores files tracked by this application to their saved state and removes tracked files that were newly created. It does not remove unrelated mods installed by another manager or repair every file in the game. If files remain locked or restoration fails, the remaining records stay tracked so you can retry after closing the game.

If the game fails to start after installing mods: close it, purge, check the red log messages, and try the clean game. If needed, verify through Steam. Then enable and install a smaller set of mods to identify the conflict. A successful export or deployment proves file checks passed; it does not prove that every mod works with the current game build.

The stock snapshot is for merging. Deployment backups are for undoing changes. Preserve both if you need recovery. Export Mod Library creates a portable ZIP of every library mod, including disabled mods, their order, categories and option selections. Import Library accepts that ZIP directly, an extracted library folder, or a folder/ZIP containing zipped mods. Imported mods are appended to your existing library and are not deployed until you use Merge and Install All. Keep a separate copy of App Data if you also need your stock snapshots, deployment backups or application settings.

## HELLFORGE SUPPORT

Select the HellForge installation folder (containing HellForge.exe or hellforge-install.json) in Merge and Deploy. Its game and data subfolders are also recognized. Audio Studio follows that deployment copy when opened. Current releases use the mod-management CLI; older Windows releases use the documented mods folder and settings, with running-session checks. On Linux, set PROTON and use a HellForge release with the mod-management CLI.

Import HellForge ZIP, 7z or RAR packages, complete extracted folders, or select a mod manifest to import its whole folder. Native hellforge-mod.json/data/stats packages, the older bts-mod.json alias, HD2Runtime and Lua mods importing its API are preserved with their JSON specs, native code, sources and Lua layout. HellForge handles compilation, dependency checks and staging; a mod still needs a compatible game/engine/SDK and its required runtimes.

Merge and Install All synchronizes enabled library packages, pack options and priority through HellForge. Built-in Hidden Content Unlocker, Stratagem Bounce Removed and Consistent Vaulting sealed-data profiles apply only to regular game installations. HellForge manages its own game copy and bundled fixes. Open HellForge with Launch Game, then press PLAY in its launcher.

In HellForge mode, gameplay editor buttons open the HellForge Stats Editor. Import named stats or read F8 changes, search and edit values, then export a checked ZIP into Mod Library. Capture as mod reads Local Stats without modifying it. Local Stats applies after packaged mods, so reset conflicting in-game edits when testing an export. The checker validates names and values; runtime layout checks still happen in-game.

Steam-only built-in tweaks are disabled in HellForge mode. Sealed .dl_bin mods and SHODAN/ModDiverEditor presets are not automatically converted to HellForge stats. Data Bot checks native stats and builds native data specs in temporary storage against the selected copy; it cannot automatically port arbitrary Steam binary patches. Library backup/import works in either mode. See HELLFORGE.md for the workflow and remaining limits.

Purge All Mods removes only HellForge packages installed through Laboratory, tracked separately per installation. Existing mods with the same identity are refused before replacement; manage that copy in HellForge first. Close any running game session before changing mods. Keep Bingus Shared Loader and HD2Runtime installed for mods requiring them. Validation here cannot establish in-game compatibility.

## MOD CREATOR — CHOOSING A TOOL

Native Game Data Editor: browse supported generated data files, search entries and edit named properties on Windows or Linux. This is the simplest route for supported stat edits. It exports a separate mod copy; it does not directly change the installed game.

SHODAN is an external Windows editor. ModDiverEditor combines CCM and SHODAN and runs on Windows or Linux through Wine. Close an editor before replacing its files with an update. Use the output-folder buttons to find saved presets and captured mods.

Capture Game as Mod: for changes already written to game data by an external editor. Start from a known clean stock snapshot, purge any Laboratory deployment, make the editor changes, then capture. The capture creates reusable mod output and portable packages. Avoid mixing unrelated changes into one capture.

Hidden Equipment Unlock: uses the supplied NoMoFOMO HD REMIX 0.5.4 profiles. Configure Unlock Categories chooses cosmetic groups and optional colored B-01 Extra Padding. Include with Install All controls whether it participates. The release includes verified built-in outputs for its supported game baseline and default selections. Deployment adopts matching outputs automatically and prepares missing results for other builds or option selections. UPDATE/REPAIR built-in mods remains available for an explicit refresh. These profiles do not include every operation of the upstream Windows installer.

Chef Shared Loader: required for compatible Lua mods. Add it from Tools, import your compatible Lua mods, then deploy. Plain data mods do not need a Lua loader. For regular game installations, native DLL/ASI/EXE injectors are not installed by Laboratory. Loader compatibility is determined by Chef and the game.

## VISUAL & AUDIO MOD CREATOR

Open Audio Studio from Mod Creator. Its four tabs cover Audio studio, Visual assets, Finish & export, and Guide & shortcuts. The handbook explains first steps, audio replacement, volume, bulk selection, visual assets, combined mods, installation and troubleshooting. Press F1 to open it. Back to Mod Creator returns to the previous page.

Audio studio reads your installed Helldivers 2 game files. Scan installed game finds Steam libraries; Choose game folder selects another installation. The first scan and scans after a game update can take longer. The app caches an index and extracts previews on demand; no extracted game sounds ship with the editor.

Browse categories such as Weapons > Primary Weapons > AR-23 Liberator. Search collections or filter the sound list. Every row has a display name; unidentified clips use numbered group/take labels. Save sound name stores your own label locally. All game archives includes audio that the named catalogue has not classified yet.

Create a project and choose its .audi file before editing. Play original previews the installed sound and its waveform. A moving cyan line and elapsed-time counter show the playback position; Stop resets them. More options holds trimming, mute, custom names and technical details. Quick guide explains the three-step workflow. Import audio file accepts WAV, MP3, FLAC, OGG, M4A, WEM and other supported audio formats. Play edited previews your replacement and saved gain. Stop ends playback.

Gain is measured in dB and applies to original audio or a replacement. Ctrl-click or Shift-click to select multiple sounds: Apply volume sets the displayed absolute dB value on all of them in one undo step, preserving each replacement’s timing. Single-sound Apply volume also saves timing. Other actions use the first selected sound. Start and End in seconds under More options trim a replacement into a new file; the original input stays intact. Mute sound stages silence. Restore original removes its replacement and gain. Audio edits save automatically.

Finish & export (Ctrl+E) creates one manager-ready ZIP from the current audio project, visual replacements, or both. You can add previously finished patch ZIPs using their default options. The exporter includes a cosmetic-pack manifest and matching sidecars, retains native resource metadata, verifies the result, and rejects conflicting resources before replacing a previous export. Add to Mod Library is selected by default; deployment remains a separate action. Keep the .audi project and referenced audio together for later editing. Use the same target game build and test playback in game.

Visual assets · Advanced retains native resource replacement. Open a source mod ZIP or archive with matching sidecars, select a texture, material, model or other resource, and choose Replace from donor mod. Choose a matching resource in the in-app donor selector. Native bundles contain resource.json, main.bin, stream.bin and gpu.bin. Texture conversion and painting require external authoring tools. Export mod ZIP saves the staged native replacements.

Audio Studio uses a bundled audio engine under MPL-2.0, with a separate ModDiver interface and integration. Source, catalogue provenance and third-party conversion-tool notices are included under vendor/audio_engine. Windows includes the audio tools and Python extensions. Linux Audio Studio requires Python 3.12+, lz4, Pillow, FFmpeg/ffprobe, vgmstream-cli and wav2wem on PATH; the rest of Laboratory retains its existing Linux requirements.

The three built-in mods are Hidden Content Unlocker (NoMoFOMO 0.5.4), Stratagem Bounce Removed (Stratagem Balls Stay Put 1.0.4) and Consistent Vaulting (1.2.0 main profile). The two gameplay profiles have separate Include with Install All checkboxes in Tools, enabled by default for new settings. Saved choices are preserved. They use the supplied sealed data payloads directly, without running upstream boot-script installers. Verified release-built outputs are included for Steam build 26251122 and default options. Exact clean-input and recipe checks prevent using them on a different build or option selection. Deployment restores a matching prepared output into its verified cache automatically; if none matches, it prepares the selected mods automatically before any game writes. UPDATE/REPAIR built-in mods remains available for manual refresh. Repair data may be downloaded when a different build requires adaptation. Install All applies the data through normal deployment; Purge All Mods restores the managed original immediately. Turning a checkbox off affects the next installation; purge an installed copy to restore it. Other mods changing the same files may conflict; the merge log reports whole-file fallback.

## NATIVE EDITOR — NAMED STATS

Choose Open Native Data Editor on the Mod Creator page. Select Open Game Database and choose data/game, or open a data file and load its matching dl_library.dl_typelib. The type library and data file must come from the same game version.

Choose a file on the left and a record in the middle. Search matches entry labels, and Previous/Next navigate lists of 300 records. Double-click an editable property on the right. Numeric fields retain their actual data type. Enum dropdowns offer values defined by the installed schema.

Not every name is recoverable: the supplied game type library has stripped field-name strings. Layout-checked reference labels cover part of the database. Unknown records are marked, and unresolved fields, unions and unsafe references remain read-only. Coverage Report describes the loaded schema. Rename Entry changes a personal display label only, not a game ID.

Export Edited File saves a separate generated_*.dl_bin file. Keep its original filename, put it in its own mod folder, import that folder and deploy. Normal export preserves the content hash and verifies the resealed output. If an edited Float32 value needs a tiny correction, you see the requested and resulting values before saving.

Schema footer export is an experimental opt-in for some dynamic layouts. It preserves exact edited values by adding correction padding, but is not game-tested for every file family. It can force whole-file conflict resolution when lengths change. Leave it off unless you understand and test that workflow. Adding/removing records is not supported.

## DATA DECODER — ADVANCED MODDING

DATA BOT downloads verified repair data for Steam builds 26251122 and 26088801 from a separate GitHub release when a repair job needs it. Internet access and temporary disk space are required. Downloaded ZIPs and extracted repair data are deleted when the job finishes or fails; another job downloads them again. Your own captured and imported baselines remain in ModDiver Lab Baseline Data beside local app data. Delete Local Data preserves that history; Uninstall deletes it. Mods from other builds may still need the matching historical baseline.

DATA BOT saves repaired mods as BotRepaired- followed by the original mod name. EXPORT REPAIRED MOD opens the saved folder. PURGE REPAIRED MOD STORAGE deletes the bot's saved outputs; Clear Log clears its report. Archive stores only repair inputs (game data tables and archive groups with their sidecars), excluding NXA packages and other unused files. Old full captures are trimmed automatically on the next capture.

The Data Decoder GUIDE button opens the complete raw-editing guide. It supports sealed generated_*.dl_bin files containing LDLD blocks and supported uncompressed Stingray archives / .patch_N containers. It does not decode every proprietary resource type into a visual editor.

For .dl_bin files, select a block and edit hex, UInt32 or Float32 values. Switching the view does not convert underlying types. An apparent decimal value may actually be an ID or pointer. Preserve lengths and offsets; Apply Edit stages changes. Export Repacked File writes a separate validated file.

For archives, open the main archive and keep matching .stream and .gpu_resources sidecars beside it. Inspect the main/stream/GPU payloads or import a replacement. Recognized Lua source can be edited as text. Export the matching file group together with the correct archive ID and .patch_N name. Compressed variants and general model/texture/audio conversion are not implemented.

Hash verification cannot validate the gameplay meaning of an edit. Use the matching clean baseline, preserve backups, change a small number of known fields, and test the exported mod. Do not distribute copies of the game database as a substitute for a documented mod package.

## MODDER REFERENCE — PACKAGES AND MERGING

A portable data mod folder can contain data/game/generated_name.dl_bin with the original filename. The importer also recognizes supported loose generated files, archive patch groups, Arsenal manifests/options and YAO/QET-signed stream descriptors. Use descriptive mod names and include a supported preview image such as preview.png.

For same-length data, the engine compares mods with stock and combines changed byte ranges. When edits overlap, library priority decides the winner. Logs report the target, record index for known fixed-row tables, byte range, both mods, and winner. If files change length or a correction cannot be verified, the engine may select the top-priority whole-file candidate and reports the fallback. Do not assume all changes survived a fallback.

Keep related archive sidecars together. Patch-number collisions are renumbered during deployment; do not rely on a package retaining a particular .patch_N number in the game. The LOADERS toggle controls whether that category deploys first or last. A loader update must be deployed before the game uses it.

Capture output can also include an Arsenal/YAO data pack for other managers. Follow that package’s generated instructions; its loader workflow differs from importing plain data files back into Laboratory. Avoid combining multiple boot replacements without understanding their compatibility.

For bug reports, use Copy Log in the Log tab. Include the app and game versions, source format, exact steps, expected result and actual result. Remove personal paths if you do not want to share them. Logs and reports are not sent automatically.

## PROJECT, LICENSES AND SUPPORT

ModDiver Laboratory will forever be free and open-source. Support is completely optional. The SUPPORT button offers Patreon and Ko-fi. No account, subscription or telemetry is required to use the app. Network access is used when checking/downloading updates, downloading temporary repair data, or opening a link.

• SHODAN — Stat Editor and game-data tooling
• Combined Community Mods contributors — the combined editor
• Chef chfb — Chef Shared Loader
• Medic 3048 — File Mod Merger
• Cowboy Bingus — Bingus Shared Loader and Vanilla+ Megapack
• huffdesigns — NoMoFOMO
• HD REMIX contributors — updated cosmetic profiles and correction references
• Filediver contributors — public name dictionaries and schema-layout references

• KNOT - ModDiver Laboratory
• Yao - ModDiver Laboratory and Merge Engine

Third-party work retains its own licenses and notices, supplied with the source and LICENSES.md. This program is a community project, not an official Helldivers 2 tool. It does not bypass anti-cheat. Thanks to the community for sharing tools, research and testing.
