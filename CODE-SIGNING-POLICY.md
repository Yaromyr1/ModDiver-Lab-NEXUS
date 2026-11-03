# Code signing policy

Status: preparation only. ModDiver Laboratory has not yet applied to or been
approved by SignPath Foundation. Existing downloads remain unsigned.

If approved, the planned service attribution is:
"Free code signing provided by [SignPath.io](https://signpath.io), certificate
by [SignPath Foundation](https://signpath.org)."
This is a proposed arrangement, not a claim of sponsorship or approval.

## Scope and approvals

The proposed signing target is the ModDiver Laboratory Windows launcher built
from this project's public source on a GitHub-hosted runner. Third-party Python,
audio tools, DLLs and extension modules must not be signed with the project's
Foundation certificate. The modified Python GUI interpreter embedded in the
launcher requires explicit eligibility clarification from SignPath before
production signing is enabled.

Proposed committer, reviewer and signing approver: [Yaromyr1](https://github.com/Yaromyr1).
One maintainer may perform all three roles. External contributions receive
maintainer review. Every production signing request requires manual approval
in SignPath, after checking its source commit, build log, dependency inventory
and release version. MFA must be enabled for GitHub and SignPath before activation;
this document does not assert that MFA is already configured.

The workflow defaults to unsigned builds. A signed release must pass signature
verification and must have its archive and checksums regenerated from the signed
EXE. An unsigned artifact must never be described as signed. Signing does not
certify that software is malware-free or guarantee antivirus clearance.

## Privacy and system changes

See [PRIVACY.md](PRIVACY.md) for the current source-inspection findings and known
network functions. Privacy review is still pending; no unverified promise of
zero network traffic is made. Installation and removal are described in
the source repository's INSTALLATION.md and the packaged NEXUS-README.md. The
Nexus package's uninstall manifest tracks package-owned files. The app provides
an Uninstall control that warns before deleting local settings, libraries,
backups and archives; users should restore managed game changes and export
anything they want to keep before using it. This preparation has not exercised
that destructive operation.

Before applying, link this policy from the public repository home page and all
download/release pages. The local preparation files have not been published.
