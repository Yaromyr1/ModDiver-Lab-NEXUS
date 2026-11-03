# Native Game Data Editor — General / Nexus

Open **MOD CREATOR → Open Native Data Editor**. The editor now browses the installed
game-data database, searches records and exposes typed, named properties across
many file families. It uses Python/Tk on Windows and Linux, without opening the
Windows SHODAN or CCM applications.

## Start editing

1. Select **Open Game Database** and choose Helldivers 2's `data/game` folder.
   This loads automatically when the app's configured game folder is valid.
   The editor reads `dl_library.dl_typelib` from that folder. It must match the
   game version of the data files being edited.
2. Select a file in the left pane. Select a record in the middle pane, or type
   part of its name in the search box. Large lists show 300 records per page;
   Previous and Next move through the results.
3. Double-click a verified editable property on the right. Integers remain
   integers; floating-point values remain floats. Enum properties offer a list
   of values declared by the installed schema, with names where known.
4. Select **Export Edited File**. Save into a separate mod folder, keeping the
   original `generated_*.dl_bin` filename. Export cannot overwrite the input or
   write inside the app's configured game folder.
5. Add the export folder to Mod Library, enable it, and use Merge and Install All.
   Export does not deploy anything. Purge restores the normal managed backup.

**Open Data File** also accepts an individual data file. If its folder has no
type library, use **Load Type Library** to select the matching one first.
Opening another file or closing the editor asks before discarding staged edits.

## Names and coverage

The supplied type library contains types and offsets, but its field-name strings
are stripped. Public Filediver layouts and the bundled SHODAN/HD REMIX metadata
recover part of the missing information. Reference labels are accepted only for
matching offsets, widths and types; a mismatch stops subsequent label matching.
Some entry names are internal resource paths, rather than localized in-game names.

The supplied files expose **116,542 records** across 54 readable LDLD files,
including collection roots and resource-index records. **46,806 records have
resolved names or exact resource associations**. Another **69,344 records are
mapped** by resource/hash ID, declared enum identity, collection role, or empty
slot status (37,146 empty slots). **392 records remain unresolved**. The schema contains 1,208 types and 7,349 member definitions;
1,150 member labels are recovered. These are schema definitions, not a count of
unique gameplay stats or a claim that every record can be edited.

Named examples include damage/durable damage, armour penetration, explosion
radii, arc speed, beam length, weapon recoil/ergonomics and stratagem cooldowns.
Armour availability/passive selection and passive effect values remain available.

Unresolved entry names are marked explicitly. **Rename Entry** lets you assign
a personal display label; it does not change the game's ID or supply a missing
field meaning. Labels are tied to the source file's content fingerprint so they
are not silently reused for a different game build. Unresolved properties,
unions, pointers and identifier/reference fields are read-only. The existing
Data Decoder remains available for deliberate raw-byte work.

General and Nexus use the same name metadata and mapping rules. Resource-index
links remain searchable by hexadecimal resource ID when a name is unavailable.
Enum mappings show the declared schema type and value, rather than guessing a
gameplay name. Empty zero-filled entity/index slots are identified separately.
A mapped identity or resource association does not supply an unknown field
meaning or enable editing it. Nexus retains the 170 shared weapon display names
without requiring the external SHODAN application bundle.

`generated_resource_swap.dl_bin` has no supported LDLD blocks. Nested entity-delta
arrays also remain unsupported. See **Coverage Report** in the editor and the
bundled `NATIVE-EDITOR-COVERAGE.md` / `.json` for the file-by-file audit. Adding or
removing records, converting assets, and reproducing every SHODAN/CCM feature
are outside this editor's current support.

## Export and verification

With no edits, export preserves the sealed file byte-for-byte. Normal edited
export corrects reserved header bytes where possible, reseals the file, decrypts
it again and checks its structure and original content hash. Some single-block
files need a small change to an explicitly edited Float32 value; the editor shows
the requested and resulting values for approval before saving. A layout without
a working correction stops export. On Linux the fallback requires LuaJIT and
may be slower than the portable correction path.

**Schema footer export (experimental)** is off by default. When explicitly
enabled, it validates the final block's dynamic layout and may append correction
padding to preserve exact edited values. Original payload bytes are checked
against the requested edits. This method has been verified by decoding and
reopening workspace exports, but has not been tested in-game for these additional
file types. It is separate from the existing HD REMIX armour correction.
Changing file length can also make the merge engine select a whole-file fallback
instead of combining overlapping mods; inspect the deployment log.

The supplied database was audited without modifying the game. Automated tests
cover schema bounds, reference mismatches, scalar types, enum constraints,
hash correction, archive/data round trips, merge/restore and updater behavior.
Representative real-file edits were exported and reopened, and UI checks covered
pagination, searching, property display and enum selection. Linux runtime
execution and in-game behavior have not been verified in this Windows workspace.

## Hidden Equipment Unlock — HD REMIX 0.5.2

The previous HD REMIX integration is retained. Configure Unlock Categories in
Tools selects six cosmetic groups and optional colored B-01 Extra Padding.
All cosmetic groups are enabled by default; Extra Padding is off by default and
requires validation of the native passive. Include with Install All controls
deployment participation. Configuration changes apply on the next installation.

The profile witnesses must match supported game build 26088801. A mismatch,
invalid layout or conflicting availability field stops deployment. Cosmetic
changes are applied after merging armour mods, preserving unrelated edits.
Purge uses Laboratory's original-file backups. Upstream ship/Stratagem Hero,
Luna and standalone installer/cleanup operations are not included.

Upstream sources, profiles and licenses are preserved under `source/vendor/`.
This is a Laboratory editor, not an official Linux port of SHODAN or CCM.
