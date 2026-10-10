# Windows releases

Droplet Vision Windows builds bundle Python, Qt and the supported Cine backend.
No separate Python environment or source checkout is needed. Beta binaries are
unsigned; use only releases from the [project repository](https://github.com/xiaorouqiuzi-ai/droplet--vision/releases).
Draft releases are visible to maintainers only until they are published.

## Portable ZIP

Extract the **entire** ZIP to a writable folder and run `DropletVision.exe`.
Keep `_internal` beside the executable. Moving the executable alone will break
its dependencies. This distribution does not register file associations.

## Installer and file associations

The installer normally uses Program Files and creates a Start Menu shortcut.
A desktop shortcut is selected by default. Package types `.dvapkg` and legacy
`.dvrpkg` are registered; association of `.cine` is optional and unchecked.
Existing Windows default-app choices are respected. If Windows asks, select
Droplet Vision in **Open with**. The file-open command quotes both the executable
and the filename, including paths containing spaces or Chinese characters.

The same executable also accepts a file from a terminal:

```powershell
.\DropletVision.exe "experiment.cine"
.\DropletVision.exe "annotation task.dvapkg"
.\DropletVision.exe "legacy.dvrpkg"
```

## User data and uninstalling

Frozen builds put default exports, annotations, autosaves, packages and sessions
under `%LOCALAPPDATA%\DropletVision`. Language preferences use the existing
per-user Qt settings. Explicit Save As destinations remain your choice.
Source-checkout launches retain their `outputs/` defaults.

Uninstall through Windows Apps or the generated uninstaller. It removes owned
program files, shortcuts and association registrations, **not** user annotations,
packages or the application user-data directory. Back up scientific work normally.

## Troubleshooting

- Missing DLL or Qt Windows platform plugin: extract the entire ZIP again and
  verify its SHA-256. Do not copy DLLs from another Qt installation.
- Package integrity failure: retain the original file and obtain a fresh copy;
  do not bypass checksum validation.
- Read-only package: use Save Annotation Package As to a writable location.
- Missing frames in package mode: only frames physically included in the package
  are available. Opening a package does not require the source Cine.
- Report the application version, Windows version and error text with a
  reproducible example that can be shared safely.

## Building from source

Use 64-bit Windows and a dedicated Python environment with the repository's
`cine`, `ui` and `release` extras. The first candidate is built with Python 3.12.

```powershell
python -m pip install -e ".[cine,ui,release]"
python -m pip check
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
python scripts/check_docs_links.py
git diff --check
python scripts/build_windows_release.py
```

Install Inno Setup 6 to produce the optional Setup executable. The build script
discovers `ISCC.exe` or accepts `--iscc <path>`. If it was installed after the
portable build, use `--installer-only` to package that same portable directory.
Version metadata comes from `src/droplet_vision/_version.py`; the Windows version
resource is generated under `build/windows/`. The spec is
`packaging/DropletVision.spec`, and the installer definition is
`packaging/DropletVision.iss`.

Generated assets under `release/<tag>/` include the onedir distribution, ZIP,
Setup executable when available, release notes and `SHA256SUMS.txt`. They are
ignored by Git. File ordering in the ZIP is stable; bit-identical builds across
toolchains are not promised.

Validate the actual executable after extracting the ZIP outside the checkout,
with `PYTHONPATH` cleared and development paths removed from `PATH`. Test Cine,
package editing, Quick Save and file arguments. Also test install/uninstall and
associations. An isolated-directory smoke on a development machine does not
replace validation in a clean Windows VM.

See [Getting Started](getting_started.md) and [Annotation Packages](annotation_package.md)
for the application workflows. TIME64, raw pixel and annotation policies remain
unchanged by packaging.
