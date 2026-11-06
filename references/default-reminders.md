# Default reminders for refinements of the same deliverable

Read this when a user explicitly asks to enable reminders by default, without
having to invoke the skill at the start of each task. This is a persistent Codex
instruction, not an event hook, daemon, timer, or permission to delete files.
Installing or updating the skill alone must not silently install global rules.

## Enable the default when authorized

Follow the official [AGENTS.md discovery rules](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
Use the active Codex home (`CODEX_HOME`, otherwise `~/.codex`). At global scope,
Codex reads a nonempty `AGENTS.override.md` before `AGENTS.md`; inspect both and
update the effective file. Read and preserve all unrelated instructions. If the
user wants only one project, update that project's effective instructions instead.
Do not read chat archives or change memory storage to configure this preference.

Append or replace only this marked section. Make the update atomic and preserve
file permissions. If a marker is unbalanced/duplicated, inspect rather than
discard other text. On repeated configuration, update the same block once.

```markdown
<!-- codex-disk-maintenance:begin -->
## Default cleanup reminders for iterative deliverables

- When this task produces file deliverables or refines an existing result,
  proactively load `codex-disk-maintenance` from the installed skills directory
  (`${CODEX_HOME:-$HOME/.codex}/skills/codex-disk-maintenance/SKILL.md` when present).
  Do not require the user to remember an invocation phrase. If unavailable,
  report that limitation without installing tools or deleting anything.
- Record successful deliveries and their necessary sources/dependencies with
  stable project/task/chat IDs. Only refinements of the SAME original result
  with the same purpose/content scope may form an improvement chain. Use the
  current request and actual editing process as evidence, recorded through
  `--improves` and `--improvement-evidence`. Changed wording/layout/data fixes
  can be improvements; byte equality is not required. Filename, timestamp,
  format or similarity alone is insufficient evidence.
- New content, a different topic/data scope, independent alternatives and
  uncertain relationships remain separate/protected, without replacement or
  improvement edges. Do not add edges just to make results eligible for cleanup.
  Never manufacture backup/version copies merely to track them or sweep unrelated
  folders; overwritten files have no separate old result to reclaim.
- After at least three successful current-chat deliveries in one evidenced
  improvement chain, run the skill's reminder check. Offer only eligible
  superseded results, once per batch, with actual scope/count/size estimates.
  A default reminder is not deletion authorization: clean only after the user
  directly confirms that concrete pending offer (for example, replies "需要").
  No reply or a refusal means retain the files.
- Before authorized cleanup, update and protect the task's sole lessons MD.
  Preserve final bundles, necessary editable sources/assets, independent content,
  chat history and memory. Respect read-only requests and requests to stop
  reminders; do not install background jobs, clear caches or weaken checks.
<!-- codex-disk-maintenance:end -->
```

Codex builds its instruction chain at run start. A new chat/run should load the
default; an already running chat may need an explicit instruction to reload the
updated guidance. Project overrides and higher-priority instructions can affect
whether it is used. Do not promise an unconditional per-chat callback.

## Same-result decision examples

| Evidence in the current task | Treatment |
| --- | --- |
| Fix labels and contrast in the previously delivered figure, retaining its subject/data scope | Record an improvement edge with that factual basis |
| Revise the previous report's wording and correct an error, preserving its purpose/scope | Record an improvement edge; protect required original sources |
| Produce a separate report on a different topic or a different data/time scope | Separate artifact; retain both |
| Generate alternatives A and B for comparison | Keep independent branches; choosing a winner alone does not establish a refinement edge |
| Two filenames share `v1`/`v2` or have similar text, without observed editing lineage | Keep both; no inferred improvement edge |
| Edit a file in place without leaving a separate previous output | Do not create an extra snapshot or claim reclaimable history |

The agent evaluates the semantic/intent relationship using available task
evidence. The standard-library executor checks declared edges and evidence,
metadata and permissions; it does not understand arbitrary file contents or
prove semantic identity. When uncertain, preserve the results quietly.
