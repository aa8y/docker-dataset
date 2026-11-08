# AGENTS.md: docker-dataset engineering guide

## Scope and sources of truth

These instructions apply to this repository and every agent that works in it.
docker-dataset builds Docker images that hold sample databases.
The engines are PostgreSQL, MariaDB (as MySQL), CockroachDB, SQLite, DuckDB, ClickHouse, Apache Druid, and Apache Pinot.
`manifest.yml` declares every image tag, and `dave` builds, tests, and publishes the tags.

Read the current user request and README.md first.
Then read the files under `docs/`, the code, the tests, and the internal plans that the work touches.
Actual code and current test results establish implemented behavior.
Past plans, reports, and earlier green runs do not prove how the code behaves now.
Do not refer to absent tools, skills, or documents as available project dependencies.
If instructions conflict, explain the conflict before dependent work starts.
`CLAUDE.md` is a symbolic link to this file, so Claude Code loads the same text. Edit `AGENTS.md` only.
This guide adapts the guides of the `athena` and `crom` repositories. The owner asked for it on 2026-11-08.

## Writing rules

Write all free text in simple English, in the spirit of ASD-STE100 Simplified Technical English.
Free text includes this guide, README.md, files under `docs/`, commit messages, plans, reports, error messages, and chat replies.
The rules do not apply to code, identifiers, commands, file paths, quoted errors, or product names.

- Keep procedural sentences to 20 words and descriptive sentences to 25 words.
- Give one instruction per sentence. Put the condition before the command: "If the build fails, read the log."
- Use simple tenses and the active voice. Name the actor.
- Use the modals `can`, `will`, and `must`. Do not use `should`, `would`, `may`, `might`, or `could`.
- Do not use contractions, semicolons, or em-dashes.
- Use one word for one meaning. Write `make sure that` instead of `check`, `verify`, `confirm`, or `validate`. Write `configuration` instead of `config`, `settings`, or `options`.
- Define a concept term at its first use, in under ten words. Do not define product names or standard names.
- State the fact, not its importance. Do not write `simply`, `seamlessly`, `robust`, `powerful`, `crucial`, or `leverage`.
- Do not use bold lead-ins, bold as emphasis, or emoji.
- Use a vertical list only for three or more parallel items or steps.
- Use American spelling.

## Staff-level planning

Plan every feature, image change, and non-trivial bug fix before implementation.
Use Astra for OpenAI planning, or Fable or Opus for Anthropic planning.
Record the actual model identifier and do not invent a model identity.
The planner owns the outcome and reviews every task result.
The planner takes the role of a Staff Software Engineer, a Staff Security Engineer, or another relevant Staff-level specialist.
Name the relevant disciplines and explain decisions, risks, and tradeoffs.
Relevant disciplines include data engineering, each database engine, container images, supply chain security, CI, and registry operations.

The planner must complete these steps:

1. Inspect affected code, Dockerfiles, `manifest.yml`, tests, CI workflows, expected files, and earlier plans.
2. For bugs, record the trigger, expected behavior, actual behavior, and reproduction or an evidence-backed hypothesis.
3. Define scope, acceptance criteria, constraints, exclusions, risks, and open questions.
4. Include each affected engine and architecture, image provenance, and the Docker Hub pull quota where relevant.
5. Split work into tasks with stable IDs such as `T01`, `T02`, and `T99` for verification.
6. Give every task dependencies and keep the dependency graph free of cycles.
7. Before parallel work, define interface contracts and assign each shared file to one owner.
8. Include integration, validation, rollout, and rollback tasks where relevant.
9. Make sure that every dependency exists and every task has an owner, labels, acceptance criteria, validation, and commit outcome.

A DAG is a dependency graph without cycles.
Tasks execute in dependency order, and only independent tasks run concurrently.
Stories can group tasks, but grouping does not create execution dependencies.
A story is complete after all of its tasks pass final acceptance.

## Plans and work tracking

Each plan lives in `.internal/plans/YYYY-MM-DD_<slug>/`, with a `plan.md` file and its evidence.
The plan header records the actual planner model, disciplines, assumptions, approval status, and base commit.
These local plans are ignored by Git and do not appear in fresh clones or worktrees.
If a plan that you need is absent, get the plan handoff before you continue. Do not silently reconstruct approval.

A plan is either not in flight or in flight. The user's request for execution moves a plan into flight.
The task table in `plan.md` is the record of task status for this repository.
Each task row records these fields:

- The stable ID, the title, and the story.
- The scope, risks, exclusions, and file territory.
- The dependencies, as immediate predecessor IDs. A root task has an empty list.
- The labels `complexity:<level>`, `path:<kind>`, and `model:<name>`, with the reason for the rating.
- The owner and the actual execution model.
- The acceptance criteria and the validation commands.
- The status, the command results, and the actual commit identifiers.

Record every out-of-scope finding in the findings section of the plan, and tell the user about it.
A finding is a bug, risk, gap, or improvement that an agent notices outside the current task.
A finding is a record, not approval.
Subagents report findings to the orchestrator, and the orchestrator records them.
Only the orchestrator changes task status and accepts completed tasks.

## Subagents and model routing

Subagents carry out implementation and research tasks.
The orchestrator owns the DAG, reviews results, and makes integration decisions.
The orchestrator does the tasks with `owner: orchestrator`, such as integration changes and plan updates.
Use general-purpose subagents pinned to the model that the task labels select.
Split mechanical work out of high complexity tasks into lower-rated subtasks where practical.

### Task labels

Each task gets three labels. The planner sets them when it creates the task.

The complexity label tells how hard the task is: `complexity:xhigh`, `complexity:high`, `complexity:med`, `complexity:low`, or `complexity:xlow`.

The path label tells how much prior knowledge exists for the task. Use one of these labels:

- `path:well-trodden`: the method is known, and a precedent is easy to find.
- `path:part-details`: some details are available, but gaps exist.
- `path:needs-research`: little is known, and the agent must find primary sources.

The `model:<name>` label records the model that the mapping below selects, for example `model:sonnet`.

### Model mapping

| Complexity | Path | Anthropic model | OpenAI model | Typical scope |
| --- | --- | --- | --- | --- |
| xhigh | needs-research | Fable | Sol | A new engine, or a new security boundary with no precedent |
| xhigh | part-details | Opus | Sol | Publication, registry credentials, cache integrity |
| xhigh | well-trodden | Opus | Sol | High-impact work with a known method and a wide blast radius |
| high | needs-research | Opus | Sol | Engine behavior or upstream data that nobody measured yet |
| high | part-details | Opus | Sol | Major engine upgrades, shared hooks that later tasks copy |
| high | well-trodden | Sonnet | Sol | Another dataset modeled on an accepted one |
| med | any | Sonnet | Terra | Bounded changes across established interfaces |
| low, xlow | any | Haiku | Mini | Version bumps, fixtures, documentation, isolated tests |

OpenAI routing depends on complexity alone.
The model that does a task also writes the summary of that task.

Rate complexity by uncertainty, coupling, impact, and difficulty of validation.
Line count does not decide complexity.
When uncertain, choose the higher level.
If discoveries increase complexity, update the task labels and escalate the task.

Then judge the path. If all of these conditions are true, the path is `path:well-trodden`:

- A close precedent exists, in this repository or in public documentation, and the assignment names it.
- The interfaces, file territory, and acceptance checks are fixed before dispatch.
- The work needs no design decision that other tasks inherit.
- Automated tests named in the task can show that the result is correct.

If the agent must make a design choice and part of the method is known, the path is `path:part-details`.
If the result sets the pattern that later tasks copy, the path is `path:part-details` or `path:needs-research`.
If the task is research that ends in a recommendation, or if the agent must find primary sources, the path is `path:needs-research`.
Record the rationale and the precedent in the task row, and name the precedent in the assignment.

If the precedent does not fit, move the task up one model and update its labels.
If the agent cannot resolve failures by following the precedent, do the same.
Haiku moves to Sonnet, Sonnet moves to Opus, and Opus moves to Fable.
After two failed reviews, also move the task up one model.
If a required model or subagent capability is unavailable, report the limitation.
Get approval for an alternative before dependent work starts.
Never substitute models silently.

### Waves

Run subagents in waves of four to six. Finish and review a wave before the next wave starts.
A finished task is worth more than an extra parallel task.
Only tasks whose dependencies are complete can join a wave.
Do not run the Druid and Pinot integration tests at the same time, because each one needs most of the memory of a local Docker VM.

### Assignments and reports

Give each agent the full task and the relevant repository facts.
Include the absolute worktree path, dependencies, base commit, file territory, contracts, and validation commands.
End the assignment with explicit reporting requirements.
Do not pass secrets or registry credentials to agents.
Internal records do not travel into new worktrees automatically.
The orchestrator owns branches, commits, merges, and pushes, unless a task explicitly delegates an operation.
Keep concurrent file territories separate. Serialize changes to `manifest.yml`, CI workflows, and shared test scripts.

Agents report changed files, actual command results, image IDs, acceptance criteria, unresolved risks, and findings.
The orchestrator reviews the diff and the evidence independently.

## Engineering and security expectations

Audit as a Staff Software Engineer, a Staff Security Engineer, and a Data Engineer as appropriate.
Read the current code and the relevant internal notes before you change it.
Preserve unrelated user changes and existing worktrees.

Preserve the manifest-driven ETL convention and the intentional dataset aliases.
Treat fetched scripts and SQL as executable input.
Treat registry credentials, build caches, and published image digests as security boundaries.
A metadata fingerprint is a cache hint. It does not prove the integrity of downloaded content.
Bind tests and publication to immutable artifacts.

Use inert fixtures, fake network and registry tools, and disposable containers for audit probes.
Never publish images or run bulk downloads as an audit test.
Before integration tests, inspect the scripts and the available local images.
Do not mount host secrets or expose test database ports.
Never update expected row counts only to make a failure pass. Require an explained data change and value and schema checks.

For image changes, test representative datasets on each affected engine and architecture.
Record the image IDs and the source provenance.
Keep the tests of existing images separate from proof that the current checkout builds.
Make sure that data values, nulls, types, and constraints are correct, as well as row counts.
Exercise failure handling, cache invalidation, and retry behavior.
Do not do automatic broad dependency upgrades. Upgrade named packages or images for a stated reason.

Findings must separate reproduced defects, design risks, hardening recommendations, and unverified assumptions.
The internal starting points are `.internal/audits/2026-09-09/report.md` and `.internal/plans/2026-09-09-improvement-plan.md`.
Ignored notes can be absent in fresh clones. This guide remains usable without them.

## Non-interactive shell commands

Agents run shell commands without a terminal, so a yes-or-no prompt stops the agent.
On some systems `cp`, `mv`, and `rm` are aliases that add `-i` and ask before each change.
Always use the non-interactive form of these commands:

```bash
cp -f source dest
mv -f source dest
rm -f file
rm -rf directory
cp -rf source dest
```

Other commands can also prompt:

- For `scp` and `ssh`, add `-o BatchMode=yes`, so that the command fails instead of a prompt.
- For `apt-get`, add `-y`.
- For `brew`, set `HOMEBREW_NO_AUTO_UPDATE=1`.

## Branches and completion

The integration branch is `master`. Changes reach `master` through a GitHub pull request.
All changes from a plan land on a local side branch named `<slug>`, based on a recorded `master` commit.
A worktree is a separate checkout for a branch.
If a managed worktree tool is available, use it and record its returned path.
Otherwise, use `.claude/worktrees/<slug>` for a manually created worktree.
Other sessions use the primary checkout. Do not switch its branch or discard its changes.

Before you open a pull request, merge the latest `master` into the plan branch.
Resolve conflicts there and review the combined diff.
Run the required tests against that exact commit and record its identifier.
Done means merged into `master`, required tests passed, acceptance criteria met, and evidence recorded.
A failed or unavailable required test blocks completion.
After you preserve needed work, retire unused worktrees.
If the user asks, push a branch, open a pull request, or publish an image. Otherwise do not.

## Documentation and validation

Keep plans, audits, decisions, investigations, handoffs, and internal reference material under `.internal/`.
Use `.internal/audits/`, `.internal/plans/`, `.internal/reference/`, and `.internal/archive/`.
The index of internal audits and plans is `.internal/README.md`.
Before you write there, make sure that `git check-ignore .internal/x` succeeds.
`.internal/` stays local unless the user asks to share or track a document. Tell the user this when you deliver an internal document.
Never force-add internal records, and never treat ignored files as secure storage.
Never put credentials or tokens in documentation.
Keep README.md, AGENTS.md, CLAUDE.md, and the guides under `docs/` versioned. Root entry points link to internal material and do not copy it.
A build or a test must not depend on internal notes.

Plans must name the actual test commands before execution starts. [docs/testing.md](docs/testing.md) describes the test layers.

- Unit and shell tests: `python -m pytest test/unit test/shell -q`.
- Shell and manifest checks: `shellcheck -x -S warning bin/* test/integration/*.sh` and `python test/validate_manifest.py`.
- Image checks for each affected engine: `dave build -c <engine> -t <tag>`, then `dave structure-test` and `dave test` with the same flags.

The Python in CI must match the `python3` package of the Alpine builder stage. Report any difference.
Documentation-only changes require link, consistency, and diff review, but no image build.
Never report commands as passed unless they ran.
Never present historical results as current evidence.

Use `T<nn>: <summary>` for task commits and `Orchestrator: <summary>` for integration or documentation commits.
If a coauthor trailer names a model, use the actual model that wrote the change.
Report delivered outcomes, the task-to-commit mapping, validation, and remaining limitations.
