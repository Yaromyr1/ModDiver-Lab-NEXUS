# Publication status — explicit approval needed

This branch is an incomplete source-publication draft. Automatic approval review blocked publication of four source files containing fixed 32-byte game-format cryptographic keys:

- `source/core.py`
- `source/vendor/hdremix052/Source/SemanticEditor.cs`
- `source/vendor/hdremix052/Source/upstream-gamedata.lua`
- `source/vendor/shodan/app/gamedata.lua`

The containing C# file matches the already public v2.3.6 Windows release byte for byte (SHA-256 `c90815e0b6315403df765084c262d868b85176308bc694df8629f5f4a4ec8983`). The constants are used by the offline game-data format implementation. Automatic review nevertheless rejected their upload, including a retry with this provenance evidence. The blocked key values are not included in this draft.

The maintainer must explicitly authorize publication of these key-bearing files before this source draft can be completed. Do not merge or advertise it as a standalone buildable checkout yet. The documented successful builds and tests used the complete isolated local source, including the withheld files. The original project and existing release downloads remain unchanged.
