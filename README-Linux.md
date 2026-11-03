# ModDiver Laboratory 2.4.2 for Linux

The main app, mod library, merge/deploy/purge, Native Game Data Editor and Data Decoder run natively. SHODAN requires Windows. ModDiverEditor runs on Windows and on x86-64 Linux through Wine. See INSTALLATION.md for the OS list and numbered installation guides. See README.md for the full beginner guide and modder reference.

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

## NATIVE EDITOR — NAMED STATS

Choose Open Native Data Editor on the Mod Creator page. Select Open Game Database and choose data/game, or open a data file and load its matching dl_library.dl_typelib. The type library and data file must come from the same game version.

Choose a file on the left and a record in the middle. Search matches entry labels, and Previous/Next navigate lists of 300 records. Double-click an editable property on the right. Numeric fields retain their actual data type. Enum dropdowns offer values defined by the installed schema.

Not every name is recoverable: the supplied game type library has stripped field-name strings. Layout-checked reference labels cover part of the database. Unknown records are marked, and unresolved fields, unions and unsafe references remain read-only. Coverage Report describes the loaded schema. Rename Entry changes a personal display label only, not a game ID.

Export Edited File saves a separate generated_*.dl_bin file. Keep its original filename, put it in its own mod folder, import that folder and deploy. Normal export preserves the content hash and verifies the resealed output. If an edited Float32 value needs a tiny correction, you see the requested and resulting values before saving.

Schema footer export is an experimental opt-in for some dynamic layouts. It preserves exact edited values by adding correction padding, but is not game-tested for every file family. It can force whole-file conflict resolution when lengths change. Leave it off unless you understand and test that workflow. Adding/removing records is not supported.
