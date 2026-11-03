# Nexus quarantine review — published v2.3.6

The published release assets were downloaded and their SHA-256 hashes verified
against GitHub release metadata. This identifies the GitHub downloads; it does
not establish that the separate Nexus uploads have identical hashes.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| ModDiver-Laboratory-Nexus-Windows.zip | 159112690 | `771bc7e3e1c17c277d46d58d72cbd49cf7070df13de4d8f32328176bcdba9194` |
| ModDiver-Laboratory-Nexus-Linux.zip | 58817870 | `52c05e59a2b3b4fbb832f1e2c5f46a5505e670e447fbca0e4e106e1baf6efdce` |

[Published v2.3.6 release](https://github.com/Yaromyr1/ModDiver-Lab-NEXUS/releases/tag/v2.3.6).

## Inspect the actual released application source

From this repository, with Python 3.10 or newer, run:

```powershell
python scripts/restore_build_inputs.py --extract-release-source build/review-v2.3.6
```

The destination must not already exist. This downloads the pinned release assets,
verifies their complete hashes, reads the Windows launcher's embedded app resource
as data, and extracts the Windows app and Linux source into separate directories.
It does not run either downloaded application. Every extracted member is compared
with [v2.3.6-manifest.json](v2.3.6-manifest.json). The manifest records 640 Windows
application entries and 621 Linux source entries, including prebuilt components.

```text
build/review-v2.3.6/windows/yao_forge.py
build/review-v2.3.6/linux/yao_forge.py
```

Both application sources declare 2.3.6. They are kept separate because platform
packaging differs. Prebuilt EXE/DLL/PYD files are not corresponding source for
their components; consult bundled notices and the provenance audit.

Current source snapshot: [`00634710119f7047705b6c3acf0f2aafdb057f3b`](https://github.com/Yaromyr1/ModDiver-Lab-NEXUS/tree/00634710119f7047705b6c3acf0f2aafdb057f3b).

## Build provenance limitation

The full available local development tree is now **2.4.2**. Its launcher and build
tools are published in this repository with [tested build instructions](../BUILDING.md).
The original complete 2.3.6 launcher/build-tool snapshot was not identified.
Do not claim the 2.4.2 build reconstructs the 2.3.6 EXE byte for byte or that the
original 2.3.6 launcher source has been independently verified against that EXE.
The historical application sources can nevertheless be reviewed directly with
the extraction procedure above. Disclose this limitation to Nexus support.

## Suggested support message

Subject: ModDiver Laboratory 2.3.6 — Windows and Linux quarantine review

Hello Nexus Mods team,

Please review the quarantined Windows and Linux v2.3.6 uploads on our mod page:
https://www.nexusmods.com/helldivers2/mods/18393.

Source and review materials:
https://github.com/Yaromyr1/ModDiver-Lab-NEXUS

Build instructions for the currently available 2.4.2 development source:
https://github.com/Yaromyr1/ModDiver-Lab-NEXUS/blob/main/BUILDING.md

Instructions and per-file manifests for inspecting the actual published v2.3.6
Windows and Linux application sources:
https://github.com/Yaromyr1/ModDiver-Lab-NEXUS/blob/main/review/NEXUS-REVIEW.md

The repository distinguishes the current development source from the older
release. We have not identified the original complete v2.3.6 launcher/build-tool
snapshot, so we are not claiming an exact rebuild of that executable. The
published app's Python source and pinned prebuilt dependencies are available for
inspection. Outstanding third-party provenance questions are documented.

Could you identify the component or packaging check that triggered quarantine,
and advise whether you need further source/build materials or a fresh reviewed
build? Thank you.

Keep the existing Nexus uploads in place for moderation review. This file is a
draft for the maintainer; no email has been sent and no clearance is claimed.
