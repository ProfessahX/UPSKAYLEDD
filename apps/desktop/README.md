# Desktop Shell

This directory is reserved for the thin desktop shell spikes and the eventual selected shell implementation.

The shared Python engine must remain the source of truth for:
- contracts
- inspection
- preview planning
- queue state
- manifests

Desktop code must not call ffmpeg, ffprobe, VapourSynth, or vs-mlrt directly.

Current spike scaffolding:
- `apps/desktop/pyside_spike/main.py` proves a native three-zone shell can call the shared Python service layer.
- `apps/desktop/web_spike/server.py` + `apps/desktop/web_spike/static/index.html` prove the browser-shell path can call the same service layer through thin local endpoints.

Selected shell:
- `apps/desktop/pyside_app/main.py` is the active desktop-app entrypoint while the MVP moves forward on `PySide6`.
- `apps/desktop/pyside_app/controller.py` keeps session state, async work, and engine orchestration inside a single desktop-facing controller.
- `apps/desktop/pyside_app/window.py` now implements the cold-start ingest, analysis summary, workspace, queue bar, and dashboard/result-review baseline screens.
- `apps/desktop/pyside_app/widgets.py` owns the reusable native drop target, preview comparator, queue bar, and payload viewer helpers instead of duplicating them across screens.
- `src/upskayledd/desktop_entry.py` is the packaging-safe desktop entrypoint used by the Windows-first PyInstaller portable build.
- `config/desktop_ui.toml`, `config/desktop_stage_ui.toml`, and `config/desktop_copy.toml` now drive the dark-shell theme, preview defaults, stage-panel behavior, and user-facing copy outside of code.
- `config/runtime_actions.toml` now drives the shared setup guidance used by CLI output, support exports, and the PySide6 ingest surface.
- the shared runtime-location surface now lets the CLI and PySide6 shell agree on where output, preview cache, support bundles, app state, and the primary model store live.
- the ingest screen now summarizes runtime health and curated model-pack readiness while preserving the raw Doctor/model-pack tools.
- the ingest screen now also keeps a recent-target shelf with lightweight context so users can reopen a known season/file path from cold start without rebrowsing blind.
- the selected shell now also exposes support-bundle export so runtime/package troubleshooting stays inside the product instead of becoming a manual support checklist.
- the selected shell now also surfaces a calm guided next-steps list so setup friction turns into clear actions instead of raw diagnostics.
- the ingest/runtime surface now also exposes direct open-folder actions for the key runtime paths users actually care about.
- the shared doctor/setup surface now also carries runtime-platform context, and Linux-side WSL runs can emit a platform-specific setup action instead of pretending they are the same thing as the host Windows runtime.
- the summary screen now includes a batch-review surface so large folder ingests can spotlight outlier episodes before the workspace/queue flow starts.
- the summary screen now also surfaces plain-language delivery guidance for the selected lane plus concise alternate-lane notes before the user commits to the workspace or a run.
- the workspace now carries source-specific batch context so users know when they are previewing a representative episode vs. an outlier.
- the dashboard now summarizes run outcomes in plain language before the raw manifest so users can verify execution mode and stream preservation quickly.
- the dashboard now also exposes a calm batch-overview/focus layer so users can read overall progress and the current attention point without parsing the job table first.
- the dashboard now also lets users jump directly to the selected job's output folder instead of stopping at result text.
- the queue bar now reuses that same shared snapshot truth to describe the active or next-up job in plain language instead of only echoing counts.
- the current Windows distribution baseline is the checked-in PyInstaller portable flow documented under `packaging/pyinstaller/`.
- the selected shell now also uses the shared repo branding assets for the window icon and the ingest hero panel instead of ad-hoc local placeholders.
- front-facing controls now lean on config-driven hover tooltips so guidance stays available without crowding the main workspace copy.
- desktop UI polish should stay anchored to `UPSKAYLEDD_ui_ux_design_flow.md` and the local `frontend-design` + `ui-ux-pro-max-sanitized` skills.
- personal validation goals can drive QA clips, but the shipped shell must stay title-agnostic.
