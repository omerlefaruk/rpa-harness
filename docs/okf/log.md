# Directory Update Log

## 2026-07-27
* **ActiveGraph cutover (Lanes B+C+F)**: Rewrote durable OKF knowledge for the EventStore-native product — system concept, ActiveGraph runtime (write/approval/repair/reconcile/evidence), retired YAML runner historical note, automation-only CLI, MCP agent loop (replacing copilot/autopilot), and thin agent rules aligned with root `AGENTS.md`. Fixed skill path citations to `.agents/skills/rpa-harness-automation-builder`.
* **Agent issue planning**: Recorded GitHub Issues, canonical triage labels, blocker-aware `ready-for-agent` eligibility, and the repository domain-documentation convention.

## 2026-06-23
* **YAGNI core deletion acceptance**: Documented terminal-only YAML operation, run artifacts as the source of truth, and the absence of dashboard, React frontend, SQLite observability DB, class workflow runtime, local subagent framework, Office/PDF layer, and job queue from the core.
* **Ponytail package cleanup**: Recorded `pyproject.toml` plus `uv.lock` as the dependency source of truth after deleting the duplicate pip requirements mirror.

## 2026-06-22
* **Runtime deletion**: Documented YAML runner as the only workflow runtime and removed Python class discovery/run CLI references from durable OKF CLI knowledge.

## 2026-06-17
* **Creation**: Established the OKF v0.1 bundle for `rpa-harness`.
* **Automation**: Added validation, index generation, hook, and agent command manifest coverage.
