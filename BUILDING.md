# Build the Nexus edition from source

**Draft publication status:** these commands passed against the complete isolated local source. This GitHub branch currently withholds four key-bearing files pending explicit approval; it cannot build standalone until they are restored. See [publication status](review/PUBLICATION-STATUS.md).

## Version and requirements

These instructions build the Nexus-staged **2.4.2** source in `source/`.
They do not reproduce the existing v2.3.6 downloads. For those downloads, see
[the release review guide](review/NEXUS-REVIEW.md).

Use Windows with the full **CPython 3.14.3 x64 installation**, including Tcl/Tk,
and the .NET Framework C# compiler (`csc.exe`). The embeddable Python distribution
does not contain the required Tcl/Tk files. The vendored Pillow/lz4 native
extensions target CPython 3.14 on Windows x64. No pip install is needed for this
build; the app's selected third-party Python packages are included under source.

The unsigned CI workflow uses `windows-2022`. Install Git to clone this repository.
Internet access is needed to restore the pinned inputs. Run from the repository root:

```powershell
git clone https://github.com/Yaromyr1/ModDiver-Lab-NEXUS.git
cd ModDiver-Lab-NEXUS
python --version
python scripts/restore_build_inputs.py
python scripts/check_signing_inputs.py
python scripts/build_ci_runtime.py --out build/ci-runtime.zip
python build_release.py --nexus --runtime build/ci-runtime.zip --out dist/ci
```

To review a fixed revision, check out its commit SHA before running the commands.
Use `python scripts/restore_build_inputs.py --verify-only` to check existing inputs
without downloading replacements. A missing/mismatched input fails validation.
Downloaded assets are cached in `build/input-cache/` and verified by size and SHA-256;
their selected members are verified again. They are never launched by the restorer.

If the compiler is not automatically found, add this argument to the build command:

```powershell
--csc C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
```

## Outputs and verification

```text
dist/ci/nexus/ModDiver-Laboratory-Nexus-Windows.zip
dist/ci/nexus/ModDiver-Laboratory-Nexus-Linux.zip
dist/ci/nexus/SHA256SUMS.txt
```

The build stages the Nexus variant, packages the Python app, compiles the C#
launcher, embeds the app and Python runtime, then generates the Windows and Linux
downloads. Both platform archives are generated on Windows. No separate Nexus
app-update ZIP is published. Nexus excludes the external editor applications,
Chef loader bundle, network updater implementations, historical repair datasets,
and nested ZIP/7z/RAR files in the staged app payload. The Windows EXE itself embeds
app/runtime ZIP resources; these remain subject to Nexus's manual review.

The build verifies application metadata and embedded launcher version consistency.
Fresh build hashes belong to the fresh outputs, not the old release. Timestamps,
compression and compilation can change bytes; bit-for-bit reproducibility of an
existing download is not claimed. No signing request or release upload is performed.

Targeted checks (set `PYTHONPATH` so app modules are discoverable):

```powershell
$env:PYTHONPATH = "$PWD\source;$PWD\source\tests"
python -m unittest discover -s source/tests -p test_review_inputs.py -v
python -m unittest discover -s source/tests -p test_signing_pipeline.py -v
python -m unittest discover -s source/tests -p test_nexus_studio_release.py -v
```

The last suite includes Tk desktop checks and needs an interactive desktop.
Building the Linux archive is not a Linux/Proton runtime or gameplay test.

## Third-party code and binaries

Unchanged binary and large build inputs come from the hash-pinned public v2.3.6 Windows asset;
the updated wav2wem binary comes from its pinned upstream v0.1 release. Small
application code and remaining assets are tracked directly. `build-inputs.json` records
each restored file's path, size and digest. `signing/dependency-lock.json` records
the selected PE inputs. Neither file certifies safety or resolves outstanding
license/source/provenance questions. The existing audit in `signing/READINESS.md`
is historical preparation, not current signing approval.
