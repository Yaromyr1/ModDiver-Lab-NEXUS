# Nexus build third-party notices

The ModDiver Laboratory application, interface, and integrations are original project work except
for the components and game-data profiles identified below. These notices apply to those included
components and do not attribute the application itself to their authors. These auathors served as 
insperation only and none of there work is used or re-used in ModDiver Laboratory.

## Derived Code and Data

- **FileDiver contributors** — public name dictionaries and layout references used by the native
  editor, under BSD-3-Clause.
- **NoMoFOMO / Hidden Content Unlocker HD REMIX 0.5.4** — source-derived cosmetic profiles and
  validation logic under GPL-3.0-only.
- **SHODAN game-data helper** — game-data read/write and hash-correction components under GPL-3.0.
- **Stratagem Bounce Removed** — data-only profile derived from the supplied **Stratagem Balls
  Stay Put 1.0.4** package.
- **Consistent Vaulting** — data-only profile DERIVED NOT COPIED from the supplied **Consistent Vaulting
  1.1.1** package; original slide-angle values credit **CowboyBingus**.
- **Runtime components** — libsodium (ISC), LuaJIT (MIT), CPython (Python Software Foundation
  license), and Tcl/Tk (BSD-style license).

The profiles above contain gameplay data, not artwork. The ModDiver Laboratory default output-mod
icon is the project badge. No upstream installer Lua is executed by these profiles.

## Audio Studio

Audio Studio source is in `vendor/audio_engine/audioStudio/`; Other bundled audio libraries and conversion tools
retain their licenses and notices under `vendor/audio_engine/licenses/` and
`vendor/audio_engine/windows/`.The ModDiver Audio Studio interface and integration are separate
project files. No extracted game audio or preview/index cache is shipped.
