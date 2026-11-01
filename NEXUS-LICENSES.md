# Third-party notices for the Nexus build


ModDiver Laboratory is free, open-source software. It bundles or links the following third-party
work. Each item remains under its own license.

## Bundled game-data tooling

- **Filediver contributors** — public type/resource name dictionaries and Go
  layout references used by the native editor, BSD-3-Clause. Repository:
  https://github.com/xypwn/filediver . Sources, revision/provenance and the full
  copyright/license notice are preserved under `source/vendor/filediver/`.
  These references are parsed as metadata; no Filediver executable is run.
  The installed game's binary type library and game-data files are not bundled.

- **NoMoFOMO + Hidden Content Unlocker HD REMIX 0.5.4** — cosmetic profiles,
  schema validation and portable hash-correction adaptation, GPL-3.0-only.
  Supplied upstream source, COPYING and third-party notices are preserved under
  `source/vendor/hdremix052/`. The Laboratory integration implements cosmetic
  categories and optional colored B-01 Extra Padding; it does not run the
  Windows installer or its ship/legacy-cleanup operations.

- **SHODAN game-data helper** - `gamedata.lua` and the sealing/hash-correction helpers used to
  read and write game files. License: GPL-3.0.
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

## Audio studio

Audiodiver 1.4.2 by Alomare is included under MPL-2.0, with complete unmodified Python source and catalogue under `source/vendor/audio_engine/audiodiver/` (`vendor/audio_engine/` inside app packages). See its NOTICE.md and LICENSE-MPL-2.0.txt. Encoder/decoder source URLs and licences are retained in `licenses/README.txt`; lz4 and Pillow notices are retained in `windows/*.dist-info/`. The ModDiver interface and integration are separate files. No extracted game audio or preview/index cache is shipped.


Chef Shared Loader, SHODAN Stat Editor and ModDiverEditor are omitted from this build.
Source code and third-party notices: https://github.com/Yaromyr1/ModDiver-Lab
