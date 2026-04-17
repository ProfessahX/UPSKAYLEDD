# Contributing to UPSKAYLEDD

Thanks for helping with the cursed media rescue mission.

## Ground rules

- Keep changes focused and reviewable.
- Preserve the separation between desktop UI, controller, `AppService`, engine modules, and integration/adapters.
- Keep GUI and CLI on the same engine path.
- Do not quietly introduce one-off hacks for a single show if the real issue can be expressed as source traits.
- Prefer explicit fallbacks and warnings over silent degradation.
- Do not commit giant media files, model weights, local previews, or generated outputs.

## Project thesis

UPSKAYLEDD should be a reproducible restoration orchestrator, not a magical black box.

That means:

- clarity beats hidden cleverness
- truthful previews beat flashy promises
- source-aware behavior beats show-specific hacks
- conservative defaults beat aggressive fake-detail nonsense
- structural repair comes before cleanup and upscale

## Good contribution areas

- source analysis / detection
- deinterlace / IVTC / cadence heuristics
- restoration preset tuning
- preview and dashboard UX
- packaging and install reliability
- test coverage for ugly real-world edge cases
- docs that make the workflow easier to understand

## Bug reports

A good bug report should include, when possible:

- operating system
- GPU / CPU info
- input source characteristics
- stage or preset used
- what happened
- what you expected
- logs, manifest, or repro steps

If the bug is quality-related, include a short description of the artifact:

- fielding / combing
- ghosting
- cadence break
- over-sharpening
- waxy faces
- noise retention
- blown detail
- aspect ratio problems

## Pull requests

Before opening a PR:

- run the tests
- update docs if behavior changed
- do not leave debug junk behind
- do not commit local caches, previews, outputs, or weights
- call out any fallback, downgrade, or backend-specific behavior changes clearly

Before merging a PR:

- let CodeRabbit finish its review
- read every CodeRabbit finding, including nitpicks
- either implement each finding or record why it is not needed
- do not merge while CodeRabbit is still reporting or before that triage is complete

## Repo hygiene

Please avoid committing:

- `.venv/`, local env files, or secrets
- generated previews or outputs
- runtime databases and cache files
- model weights or large sample media unless explicitly intended for distribution

## Tone

You are welcome to keep the project funny.
Just do not make the codebase harder to maintain in the name of the bit.
