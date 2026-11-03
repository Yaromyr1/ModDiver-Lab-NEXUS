# Third-party notices for the Nexus build


The ModDiver Laboratory application, its interface, and its integrations are original project work,
except for the specifically identified components and game-data profiles below. These notices describe
those included components; they do not attribute the ModDiver Laboratory application to their authors.
Each listed item remains under its own license.

## Bundled game-data tooling

- **Filediver contributors** — public type/resource name dictionaries and Go
  layout references used by the native editor, BSD-3-Clause. Repository:
  https://github.com/xypwn/filediver . Sources, revision/provenance and the full
  copyright/license notice are preserved under `source/vendor/filediver/`.
  These references are parsed as metadata; no Filediver executable is run.
  The installed game's binary type library and game-data files are not bundled.

- **NoMoFOMO + Hidden Content Unlocker HD REMIX 0.5.4** — cosmetic profiles,
  schema validation and portable hash-correction adaptation, GPL-3.0-only.
  Source-derived files, GPL license identifiers, and source provenance are
  preserved under `source/vendor/hdremix052/`; the broader upstream archive is
  not redistributed. The Laboratory integration implements cosmetic
  categories and optional colored B-01 Extra Padding; it does not run the
  Windows installer or its ship/legacy-cleanup operations.

- **SHODAN game-data helper** - `gamedata.lua` and the sealing/hash-correction helpers used to
  read and write game files. License: GPL-3.0.
- **Native Editor display-name metadata** - `source/native_names.json` preserves the 170
  resource IDs and weapon display names from the bundled SHODAN 4.6.0 WEAPONS table
  for both General and Nexus. The file records the source SHA-256; no editor code
  is included in this metadata. Source table: SHODAN Stat Editor, GPL-3.0.
- **YAO DATA LOADER** - the `.stream` descriptor format understood by the parser.
- **NoMoFOMO** by **huffdesigns** - original cosmetic target lists, with credit
  retained through the supplied HD REMIX profiles and notices. The earlier
  prebuilt payload has been replaced by semantic generation from captured stock.

## Runtime libraries

- **libsodium** (`libsodium.dll`) - ISC license.
- **LuaJIT** (`lua51.dll`) - MIT license.
- **CPython** - Python Software Foundation license.
- **Tcl/Tk** - BSD-style license.

## Game assets

Bundled gameplay data is supplied as community mod payloads, rather than as a game installation.
The NoMoFOMO payload is credited above. Data-only profiles under `builtin/gameplay/` are extracted
from the user-supplied **Stratagem Balls Stay Put 1.0.4** and **Consistent Vaulting 1.1.1** packages.
Their upstream READMEs and source archive checksums are retained in each profile ZIP. Consistent
Vaulting credits CowboyBingus for the original Vanilla Plus Megapack slide-angle values.
No upstream installer Lua is executed by these profiles. The Malorian/Famas samples were used
for local format verification and are not included in the release.

## Notes

- ModDiver Laboratory is unsigned. Verify releases against the published `SHA256SUMS.txt`.
- ModDiver Laboratory does not bypass anti-cheat and only writes offline data files.

## Audio Studio

The audio engine is Audiodiver 1.4.2 by Alomare and is included under MPL-2.0. Its Python source is under `source/vendor/audio_engine/audiodiver/` (`vendor/audio_engine/audiodiver/` inside app packages). The upstream default output-mod icon is replaced by the ModDiver Laboratory badge. The catalogue and provenance are included. Notices for bundled conversion tools and libraries are under `vendor/audio_engine/licenses/` and `vendor/audio_engine/windows/`. The ModDiver Audio Studio interface and integration are separate original project files. No extracted game audio or preview/index cache is shipped. See `vendor/audio_engine/NOTICE.md` and the MPL-2.0 license at https://mozilla.org/MPL/2.0/.


Chef Shared Loader, SHODAN Stat Editor and ModDiverEditor are omitted from this build.
Source code and third-party notices: https://github.com/Yaromyr1/ModDiver-Lab
