# PySide6 App Shell

`PySide6` is the selected desktop shell for UPSKAYLEDD.

Current state:
- `main.py` launches the real selected-shell app instead of forwarding into the spike
- `controller.py` is the desktop-facing orchestration layer and persists session state through `src/upskayledd/app_service.py`
- `window.py` provides the MVP ingest, summary, workspace, queue, and dashboard/result-review screens
- `widgets.py` provides the native drop target, synced preview comparator, queue bar, and payload-viewer building blocks
- `ui_config.py` + `config/desktop_ui.toml` keep shell presentation, preview defaults, and dark-theme direction configurable outside of code
- `config/desktop_stage_ui.toml` defines stage-card labels, stage descriptions, and simple/advanced control behavior without hardcoding it into the window
- `config/desktop_copy.toml` now owns setup/status/workflow copy so messaging polish does not require code edits
- `config/desktop_copy.toml` now also owns most front-facing hover-tooltip copy so explanation stays available without cluttering the main layout
- `config/runtime_actions.toml` now owns the prioritized runtime setup guidance used by the CLI, support bundle, and ingest shell surface
- the shared runtime-location surface now feeds both the CLI and ingest shell so users can see where this install writes output/support/cache/model data
- `src/upskayledd/desktop_entry.py` now provides the PyInstaller-friendly desktop entrypoint instead of relying on source-tree-specific startup assumptions
- the shell now uses the shared repo icon and hero artwork so cold start feels branded without hardcoding asset paths into the UI
- the ingest screen now includes a runtime-readiness card that summarizes environment health and curated model-pack status in plain language
- the ingest screen now also includes a recent-target shelf with lightweight analysis context so repeat users can jump back into a previously analyzed season or file directly from cold start
- the ingest screen also exposes support-bundle export so users can package runtime/model-pack/job context without assembling it by hand
- the ingest runtime card now shows a short guided next-steps list derived from real runtime state instead of UI-only hardcoded advice
- the ingest runtime card now also shows runtime-platform context and can surface a WSL-specific setup action when the Linux-side runtime is incomplete
- the ingest runtime card now also offers direct open-folder actions for the important runtime paths instead of hiding them behind guesswork
- the summary screen now includes a batch-review table for per-source profile/outlier review before the workspace opens
- the summary screen now also includes plain-language delivery guidance for the selected encode lane plus short alternate-lane notes, so users can see preservation-vs-compatibility tradeoffs before running
- the workspace now keeps a small batch-context note visible so the selected source is framed as aligned, outlier, or manual-review worthy
- cleanup and upscale are now conservative by default but expose extra preset options in config so stronger paths are available without code edits
- the dashboard now includes a result-review compare surface that can load source vs completed output from the selected job
- the dashboard now also includes a concise run-summary layer so execution mode, stream outcomes, and fallbacks are readable without opening raw manifest JSON first
- the dashboard now also includes a batch-overview/focus panel with progress, active/completed/attention counts, and a clear "what is happening now" summary
- the dashboard now also exposes an open-output-folder action for the selected job so result review leads directly to the produced files
- the queue bar now summarizes the active or next-up job in plain language by reusing the same shared dashboard snapshot data

Current guardrails:
- desktop code still delegates engine work to `src/upskayledd/app_service.py`
- the old web spike remains reference material only
- future work should widen polish and packaging without reintroducing direct integration calls from the UI
- the current Windows portable baseline is the checked-in PyInstaller flow, and the shell now loads bundled UI config through the shared frozen-aware path helpers
- the current Windows installer baseline is the checked-in Inno Setup flow layered on top of the validated portable build
- the queue bar stays hidden when idle, and the dashboard owns retry/resume actions for selected jobs
- batch progress/focus wording now lives in `config/desktop_copy.toml` so this surface can be tuned without code edits
- switching sources clears stale preview state so the workspace cannot accidentally show the previous episode's preview
- frontend polish passes should stay grounded in `UPSKAYLEDD_ui_ux_design_flow.md` and should be reviewed through the local `frontend-design` and `ui-ux-pro-max-sanitized` skills before major UI changes land
- personal validation targets can inform QA, but the shell copy and controls stay source-class driven rather than title-specific
