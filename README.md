# ModDiver Laboratory — source-publication draft

**Incomplete draft: [four key-bearing source files await explicit publication approval](review/PUBLICATION-STATUS.md). Do not merge or use this branch as a standalone buildable checkout yet.**

This repository contains the available Nexus-staged **2.4.2 application source**,
Windows launcher source, build tools, license notices, and hash-pinned build inputs.
It also provides a verified extraction procedure for the published **2.3.6**
Windows and Linux application sources currently relevant to quarantine review.

- [Build the current source](BUILDING.md)
- [Review the published 2.3.6 files](review/NEXUS-REVIEW.md)
- [Installation and Nexus edition behavior](NEXUS-README.md)
- [Project license](LICENSE) and [third-party notices](NEXUS-LICENSES.md)

The current source is a later version than the v2.3.6 release assets. Do not use
the v2.3.6 tag's automatically generated GitHub source archive as a complete
application source snapshot: that tag originally contained only a few files.
Follow the verified extraction procedure for the actual released application.

Large prebuilt dependencies are restored from explicitly pinned public assets
and checked per file. This is not an independent rebuild of those dependencies
or evidence of malware clearance. See [build-inputs.json](build-inputs.json) and
the outstanding provenance questions in [signing/READINESS.md](signing/READINESS.md).

Source synchronization does not publish a new application release, change the
existing release downloads, request signing, or establish Nexus approval.
