# ModDiver Laboratory 2.4.2 — Nexus build

[License](LICENSE) · [Licensing scope](LICENSING.md) · [Code signing policy](CODE-SIGNING-POLICY.md)

This Windows and Linux build includes the Native Game Data Editor, Data Decoder and Audio Studio. Data Bot builds its repair reference from the user's Steam-verified game files and uses only a clean capture matching the installed build. The package contains no historical game-data repair datasets and does not download them. Source and third-party notices: https://github.com/Yaromyr1/ModDiver-Lab-NEXUS.

## Studio

The expanded handbook and shortcuts (F1), themed Finish & export workflow (Ctrl+E), and combined audio/visual manager-ready ZIP export are included. Read AUDIO-STUDIO.md. Export creates a mod package from your own projects; it does not install one automatically.

## Separate from General

Nexus uses its own ModDiverLabNexus app-data/cache folder, Nexus-named shortcuts, and ModDiver Lab Nexus Baseline Data for local repair references. It never automatically imports General settings, caches or repair datasets. Previous shared data is left untouched; use Export/Import Mod Library to transfer packages deliberately. Keep Nexus and General downloads in separate extracted folders.

## Windows

Extract the complete Windows ZIP to a normal folder and start **ModDiver Laboratory.exe**. Python is bundled. Keep the application folder together. User settings, mod library, clean-stock snapshots and recovery data are stored separately under your user profile.

## Linux

Extract the Linux ZIP into your home folder. Run **Install ModDiver.desktop**, or open a terminal in the extracted folder and run 'sh install-linux.sh'. The installer uses your distribution package manager for required system libraries; it does not use sudo to run the app.

## Disabled while Nexus reviews this build

App update controls are disabled. The app displays:

> Awaiting Nexus Mods confirmation on File Submission Guidelines and Terms of Service. This feature is disabled until further notice.

Chef Shared Loader, SHODAN Stat Editor and ModDiverEditor are not included. Import your own Chef Shared Loader ZIP, 7Z or folder through Mod Library; it is recognized automatically and placed in Loaders. Imported Chef entries remain in the library after restarting.
