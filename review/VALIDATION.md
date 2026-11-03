# Source publication validation — 3 November 2026

Validation was performed in an isolated copy of the local 2.4.2 project on Windows.
The original project, existing GitHub release assets, and Nexus uploads were not
modified by this work.

- Verified both public v2.3.6 release ZIPs against GitHub's published SHA-256 values.
- Extracted the Windows embedded app and Linux application source as data;
  verified every extracted member against the committed historical manifest.
- Restored the initially selected 22 large build inputs from the pinned cache;
  subsequently extended the same mechanism to 76 unchanged binary/large inputs.
- Replaced the isolated copy's wav2wem with the upstream v0.1 bytes matching the
  existing dependency lock and GitHub's published asset digest. The original
  local copy differed from that digest and was left untouched.
- Verified all 30 selected native binary inputs against the dependency lock.
- Passed 5 input-validation tests, 3 signing/runtime-packaging tests, and all 7
  Nexus Studio/packaging/isolation tests (15 targeted tests total).
- Built the runtime with the full installed CPython 3.14.3 x64 distribution and
  successfully compiled/generated the Windows and Linux Nexus packages using
  the documented build commands. The build performed its embedded-version checks.

Example local build outputs (not published as release assets):

| Archive | SHA-256 |
| --- | --- |
| Windows | `821706a8b2f1787bf84cb25b9ddca16d7b161323cad5529a3bae3fce0695ffb0` |
| Linux | `3b32abe66c1eee433c1911c30018051ef74a7e43df3e9da23b84150b221907f1` |

These hashes identify this local build only. Runtime installation contents,
timestamps and compilation can change later build hashes. A hosted CI run, a
Linux/Proton execution test, a gameplay test, an independent dependency rebuild,
an antivirus clearance and a byte-identical historical launcher rebuild are not
claimed by this report.

The original partial repository remains available in Git history at
[`03559af266763acd86e3b1b93db0f7018f2017fe`](https://github.com/Yaromyr1/ModDiver-Lab-NEXUS/tree/03559af266763acd86e3b1b93db0f7018f2017fe).
Its old root-level application files and checksums are superseded by the complete
source layout, build-output checksums and historical release manifest.
