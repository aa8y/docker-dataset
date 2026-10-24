# Agent instructions for docker-dataset

This is the canonical instruction file for every AI agent working in this
repository. `CLAUDE.md` is a symlink to this file.

## Documentation

Keep all internal documentation in `.internal/`: audits, plans, architecture notes, decisions, investigations, handoffs, and internal reference material. Create the directory when absent. Use `.internal/audits/`, `.internal/plans/`, `.internal/reference/`, and `.internal/archive/` as appropriate. Never put credentials or tokens in documentation.

`.internal/` is intentionally ignored by Git and stays local unless the user explicitly requests sharing or tracking particular documents. Explain this when delivering internal artifacts. Do not force-add internal documents by default. Public README, changelog, license, and these agent entry points remain at the repository root. Root agent entry points should link to internal material rather than duplicate it. The index of internal audits and plans lives in `.internal/README.md`.

## Planning authority

Plans must be created and revised by a top-level planning model: **Astra with OpenAI** or **Fable with Anthropic**. The planner adopts the role of a Staff Software Engineer, Staff Security Engineer, or another relevant Staff-level engineering specialist. Assess outcomes, risks, compatibility, and validation before breaking work down.

If the required planning model is unavailable, report the limitation and request the appropriate model or an explicit user override; do not silently substitute. Model names below are routing requirements, not a claim that every provider/model is available in the current environment.

Every implementation plan must contain:

- Stories describing user or operational outcomes, decomposed into tasks and executable subtasks.
- Stable IDs and explicit dependencies forming a directed acyclic graph (DAG). List immediate predecessor IDs; use an empty list for roots. Check for missing references and cycles.
- For every subtask: scope, complexity (**High**, **Medium**, or **Low**), assigned model, acceptance criteria, meaningful validation, and one or more intended commits with subjects. Distinguish complexity from severity and priority.
- Story/task completion criteria, execution order or parallel waves, material risks, and a definition of done. A parent completes only after its children and prerequisites pass review.

## Delegation and model routing

Stories, tasks, and subtasks are handled by subagents. The top-level planner coordinates the DAG, assigns bounded work, reviews results, and integrates completed work. Story/task coordinators use the highest complexity of their owned work; each executable subtask uses its own rating.

| Complexity | OpenAI | Anthropic |
| --- | --- | --- |
| High | Sol | Opus |
| Medium | Terra | Sonnet |
| Low | Mini | Haiku |

Use the active provider's mapping and a verified available model identifier. Do not invent identifiers or substitute another model without an explicit user override. If routing is unavailable, report the blocked assignment and continue independent authorized work. Delegate only ready nodes whose dependencies are satisfied. Give each subagent scope, owned files, prerequisites, acceptance criteria, validation, and expected commits. Avoid concurrent edits to the same files; sequence shared-file work or isolate it. Subagents report changes, checks, risks, and commit IDs. Every completed implementation subtask must produce one or more focused commits. Do not mark planned commits as completed before they exist.

## Engineering and security expectations

Audit as a Staff Software Engineer, Staff Security Engineer, and Data Engineer as appropriate. Read current code and relevant internal notes before changing it. Preserve unrelated user changes and existing worktrees. Public building/testing/attribution guides stay under `docs/`; private audit evidence, plans, decisions, and handoffs belong in `.internal/`.

The project builds sample databases for PostgreSQL, MariaDB, CockroachDB, SQLite, and DuckDB. Preserve the manifest-driven ETL convention and intentional dataset aliases. Treat fetched scripts and SQL as executable input, and registry credentials, build caches, and published image digests as security boundaries. A metadata fingerprint is a cache hint, not proof of downloaded content integrity. Bind tests and publication to immutable artifacts.

Use inert fixtures, fake network/registry tools, and disposable containers for audit probes. Never publish images or run bulk downloads as an audit test. Before integration tests, inspect the scripts and available local images. Do not mount host secrets or expose test database ports. Never update expected row counts merely to make a failure pass; require an explained data change and value/schema checks.

Run `python -m pytest test/unit -q` in the configured test environment and relevant shell/manifest checks. CI currently specifies Python 3.12; report runtime differences. For image changes, test representative datasets and each affected engine/architecture, recording image IDs and source provenance. Separate tests of existing images from proof that the current checkout builds correctly. Check data values, nulls, types, and constraints as well as row counts. Exercise failure handling, cache invalidation, and retry behavior. No automatic broad dependency upgrades.

Findings must distinguish reproduced defects, design risks, hardening recommendations, and unverified assumptions. Internal starting points: `.internal/audits/2026-09-09/report.md` and `.internal/plans/2026-09-09-improvement-plan.md`. Ignored notes may be absent in fresh clones; this policy remains usable without them.
