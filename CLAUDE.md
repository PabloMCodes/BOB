# CLAUDE.md

@AGENTS.md

## Claude Code specifics

- Run Python through `uv run` (e.g. `uv run pytest`) — never the system `python3` (3.9, missing deps).
- Work step by step per `README.MD` → Progression. Before starting a new step, ask the user clarifying questions; define its scope and test method first.
- After completing a step: run `uv run pytest`, then update that step's README row (status + measured results) and its Step section. Do not report a step complete until tests pass and the README is updated.
- Do not commit or push unless the user asks. Branch: `autoCV`.
- Keep Swift minimal and explain any Xcode setup steps the user must do manually (signing, device selection, Info.plist keys) — those can't be automated from here.
