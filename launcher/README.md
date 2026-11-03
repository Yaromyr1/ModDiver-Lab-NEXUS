# ModDiver Laboratory launcher

`launcher.cs` is the thin Windows GUI bootstrapper compiled into `ModDiver Laboratory.exe`
(launcher API 3). Updates do **not** replace it. Upgrading from API 2 requires
the full Windows download once; keep the existing App Data directory.

Layout under `%LOCALAPPDATA%\ModDiverLab`:

    python\                 CPython/Tk runtime, extracted once from the embedded runtime.zip
    app\<version>\         one immutable folder per app version (marker file .app-ok when complete)
    app\current.txt         line 1 = active version, line 2 = previous version (rollback target)
    launcher.log             launcher log (capped at 256 KB)

At start the launcher reads `current.txt` and runs `ModDiver Lab-<seed-version>.exe app\<current>\yao_forge.py`. The interpreter name includes the seed version so a new launcher installs the new icon even when an older interpreter exists. The EXE embeds
a *seed* copy of one app version (`app.zip` + `app.version`) used on first run or when it is newer than what is
installed. If the started app exits with a non-zero code within 4 seconds, the launcher switches back to the
previous version. Old version folders (and folders from pre-1.8.8 launchers) are removed on a later start, but
only when no other ModDiver process is running.

Environment passed to the app: `YAO_FORGE_DATA`, `YAO_FORGE_LEGACY_DATA`, `YAO_FORGE_EXE`,
`YAO_FORGE_LAUNCHER_API`.

The runtime remains CPython. `brand_runtime.py` copies its GUI executable and replaces
only its icon and version resources with the yellow icon and ModDiver Lab identity.
The branded copy lives beside the original interpreter and uses the same DLLs and libraries.
A startup mutex serializes extraction, and the application holds a per-user file lock
until it closes. Duplicate Windows launches attempt to focus the existing window.
The Linux bootstrap similarly serializes startup and uses the same application lock.

Embedded resources, named exactly: `app.zip`, `app.version`, `runtime.zip`, `moddiver-python.exe`. `build_release.py` compiles it
with the .NET Framework `csc.exe`; keep the source C# 5 compatible. Raise `LauncherApi` only when the
launcher/app contract changes, and raise `MIN_LAUNCHER` in `build_release.py` to match.

Build scratch files (the branded interpreter, metadata stub and app.version) are created in a temporary directory and removed after compilation. The standalone app is the ModDiver Laboratory.exe at the project root; runtime.zip in build/ is retained as the input for future builds. Do not launch runtime helpers directly.
