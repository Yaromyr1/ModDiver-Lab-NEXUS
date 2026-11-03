# SignPath preparation — November 1, 2026

Status: local preparation complete enough for review; NOT eligible for production
signing yet. No application, account, signing request or publication has occurred.

## Completed locally

- Maintainer selected GPL-3.0-only for original code; LICENSE contains the full
  GPL v3 text, copied verbatim from an existing bundled copy. LICENSING.md limits
  that grant to work owned by the maintainer.
- Draft code signing and privacy policies; proposed sole maintainer is Yaromyr1.
- Generated launcher file/product version from the actual application version.
- Locked the hashes of all 30 native binary inputs selected by Nexus staging.
- Added a clean-runtime packager with per-file provenance, a Windows CI workflow,
  a launcher-only SignPath configuration, and signed-release repackaging with
  checksum regeneration. These are preparation tools, not completed signing.

## Dependency audit

| Component | Evidence found | Still required |
| --- | --- | --- |
| CPython/Tcl/Tk | Existing release has embedded runtime; new builder records installed-runtime file hashes and preserves original binaries | Validate hosted CI runtime; retain full license notices; record setup-python run/source. Existing runtime's upstream origin is not independently established |
| Custom Python GUI EXE | brand_runtime.py modifies upstream Python resources | Ask Foundation whether this exact packaging is acceptable; do not sign this upstream binary with project credentials |
| FFmpeg/ffprobe | Exact binary hashes; GPL v3 text in audio licenses | Exact upstream version/build, download URL and corresponding source/build configuration; license text alone is insufficient |
| vgmstream and codec DLLs | Exact hashes; vgmstream notice | Pinned upstream release, origins and applicable notices for each DLL, corresponding source where required |
| wav2wem | Local SHA-256 exactly matches GitHub's published v0.1 release-asset digest; tag commit 38e916953bec63862b13b449d780d1303a1bf29c; GPL v2 text and third-party explanation; provenance JSON added beside licenses | Vendor classification reviews and complete corresponding-source obligations, including embedded encoder; no independent rebuild/audit yet |
| Pillow 12.3.0 and lz4 4.4.5 | Package metadata, license files, CPython 3.14 native extensions | Match the vendored bytes against original wheel hashes and retain wheel origin; preserve bundled codec notices |
| audioStudio 1.4.2 | Local package declares version; integration describes MPL; LICENSES.md still describes Audiodiver | Obtain exact upstream repository/revision and MPL text; reconcile old and current attribution. NOTICE.md referenced by current LICENSES.md is absent locally |
| Filediver dictionaries | SOURCE.json records repository revision, URLs and file hashes; COPYING.txt present | Verify hashes against upstream and confirm all derived files retain notices |
| HD REMIX | UPSTREAM.json records archive name/hash; files and runtime notice present | Record accessible upstream source location, full license and rights to redistributed profiles; archive hash alone is insufficient |
| SHODAN Lua/hash helpers and libsodium | Three DLLs and helper sources; general notices | Exact upstream revisions/builds, corresponding source, and complete license texts |
| Gameplay profiles/artwork | Some provenance is described in notices | Confirm rights and source for every redistributed asset; project root license cannot grant third-party rights |

These findings are a release-readiness review, not a legal opinion or a completed
malware audit. Resolve uncertain licenses from the actual upstream terms.

## Current release versus current source

The scanned EXE SHA-256 is
740f0a40c52970b56bb2f5bff7649e25ad511df07789b8a64a3bdd4ae8aed531.
The local source currently declares 2.3.4 and has audioStudio paths, while the
scanned release embeds Audiodiver paths. Do not claim the current workspace
reproduces that exact EXE. The existing dist/nexus release has been preserved.

The user reports that the separately extracted runtime.zip has no VirusTotal
detections. Their app.zip screenshot shows Bkav Pro W32.Malware.7797BC48, 1/64.
The app SHA-256 is
1db119f0df105b264061f75b9de438f44d4c85dc026de9e5e9bf40ee29607a0f,
verified against the local extracted archive. These are supplied scan results,
not an independent live scan. They do not identify which member triggered Bkav.

## Activate only after review

1. Confirm the public repository URL and synchronize this workspace with it.
   This folder currently has no .git repository; network access to GitHub failed.
2. Resolve the dependency questions above, including source availability. Publish
   the project license and link the policy from the home and download pages.
3. Run the workflow unsigned first. Compare its contents with the intended app,
   test launch/modding/audio on a clean machine, and review network behavior.
   Pin workflow actions to reviewed full commit SHAs before production activation.
4. Enable GitHub MFA. Apply at https://signpath.org/apply using APPLICATION.md.
   Create/configure SignPath when instructed and enable MFA there too.
5. Ask Foundation about the modified interpreter and the modding functionality;
   disclose the current antivirus detections. Approval is their decision.
6. Configure a GitHub.com trusted build system and the SignPath GitHub App, with
   access limited to this repository. Configure the XML artifact rules and a
   manually approved signing policy; restrict release refs through SignPath.
7. Set the GitHub secret SIGNPATH_API_TOKEN and variables
   SIGNPATH_ORGANIZATION_ID, SIGNPATH_PROJECT_SLUG,
   SIGNPATH_SIGNING_POLICY_SLUG and SIGNPATH_ARTIFACT_CONFIGURATION_SLUG.
   Keep the token out of source files and chat.
8. Change each readiness.json flag only with supporting review evidence. The
   workflow fails before submission while any flag is false. The default
   workflow produces unsigned artifacts and does not publish releases.
9. Run signing from a reviewed release commit, approve in SignPath, verify the
   returned certificate/publisher and timestamp, test the final package, and
   publish only its regenerated checksums with that exact signed build.

Sources:
- https://signpath.org/terms.html
- https://docs.signpath.io/trusted-build-systems/github
- https://docs.signpath.io/artifact-configuration/reference

See validation-results.md for checks actually performed locally.
