# Packaging Notes

Packaging work stays secondary until the shared engine and desktop shell decision gate are complete.

Near-term goals:
- support local development and CLI execution
- keep runtime/config paths explicit
- avoid installer-specific lock-in too early
- give users a support-bundle export path so runtime/package diagnostics can be shared without bundling source media or leaking full paths by default
- keep setup guidance shared and config-driven so packaging help does not fork into separate CLI/UI support stories

Current Windows-first portable path:
- install the build extra: `python -m pip install -e .[desktop-build]`
- build the selected-shell portable bundle: `python packaging/pyinstaller/build_windows_portable.py --clean`
- build and validate offscreen boot in one pass: `python packaging/pyinstaller/build_windows_portable.py --clean --validate`
- build the Windows installer from the current portable bundle: `python packaging/inno/build_windows_installer.py --skip-portable`
- rebuild the portable bundle and then build the installer in one pass: `python packaging/inno/build_windows_installer.py --clean`
- inspect the resolved runtime/output/support/model locations with: `upskayledd paths`
- the bundle lands in `dist/pyinstaller/upskayledd-desktop/`
- the installer lands in `dist/installer/UPSKAYLEDD-Setup-<version>.exe`
- the current baseline is considered healthy only after the clean build flow and the validator both pass without startup popups or missing bundled config/assets

Packaging rules:
- bundled read-only assets stay inside the PyInstaller `_internal` directory
- writable runtime state moves to the user's app-data area in frozen builds instead of writing into the bundle directory
- curated model packs resolve through configured model directories first, with the bundled VapourSynth layout treated as a fallback instead of the primary install target
- shared Windows branding assets are generated from the repo icon/header/hero files so the portable bundle and installer stay visually aligned without duplicating asset logic
- the current Windows installer baseline uses Inno Setup with a per-user install directory and an optional desktop shortcut instead of requiring admin-only system-wide installs
