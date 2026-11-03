YAO DATA LOADER v1
==================

Bundled with ModDiver Laboratory to build Arsenal data-pack ZIPs.

The loader is a boot patch. It scans data/9ba626afa44a3aa3.patch_N.stream
for YAO-DLBRIDGE/1 descriptors and applies the candidate file, keeping a
backup of the original and restoring it when the descriptor is removed.

No BSL, no FFI, no DLL. Only one boot replacement can be active.
Original package layout: YAO-LOADER-Arsenal.zip.
