# Codex Disk Maintenance

[简体中文](README.md) | **English**

Disk diagnostics, output revision management, in-chat cleanup reminders, and task closeout for Codex: **retain final deliverables, required dependencies, and memory; offer cleanup after repeated deliveries; reclaim intermediates after the user says “yes”; and maintain task lessons in one Markdown document.**

Built for macOS. Core scripts use Python 3.9+ and the standard library, with no third-party Python runtime dependencies.

> Once loaded and used in the current chat, the skill can proactively offer cleanup after repeated deliveries. Installation alone creates no background service, scheduled job, or session-end hook, and does not guarantee invocation in every chat. Use the one-sentence request below to enable it for a task.

## The simplest way to use it

Say this once when starting a task or continuing refinements:

> **Use $codex-disk-maintenance to remind me about cleanup after repeated deliveries in this task, and perform it when I reply “yes.”**

Continue refining normally. When a concrete cleanup offer appears, reply **“yes”** or **“需要”**. Codex updates the same lessons file, rechecks the offered predecessors, and removes those that pass. Reply “not now” to retain them without repeated prompts for the same results.

To organize existing results immediately:

> Use $codex-disk-maintenance to organize project deliverables, clean up intermediate versions, and update the lessons log.

For a more explicit closeout request:

> Organize the outputs from this conversation. Keep the final versions and necessary source files, and delete clearly unnecessary intermediate results. Summarize useful lessons in a single lessons Markdown file and update that same file after future changes.

You can also invoke individual workflows:

| What you need | Example request |
| --- | --- |
| Inspect disk usage | Use $codex-disk-maintenance to inspect Codex disk usage without deleting anything. |
| Remind after repeated deliveries | Use $codex-disk-maintenance to offer cleanup after repeated deliveries in this task, and perform it when I reply “yes.” |
| Manage future iterations | Use $codex-disk-maintenance for this task: keep the final deliverables and clean up superseded versions. |
| Mark a final delivery | This version is final. Keep the complete deliverable bundle and required assets. |
| Identify historical revisions | Use $codex-disk-maintenance to inspect revisions in this folder and list candidates first. |
| Close out a task | Organize project deliverables, clean up intermediate versions, and update the lessons log. |

In a new chat, explicitly naming `$codex-disk-maintenance` helps select the skill. A vague request such as “organize this project” might instead be interpreted as code or directory restructuring.

## What problem does it address?

Codex tasks can accumulate working directories, dependencies, rendered images, converted files, test outputs, and repeated revisions. A directory named `tmp` or `cache` is not sufficient evidence that everything inside it is disposable.

The skill combines two types of capability:

- **Deterministic scripts:** measure directories, compare baselines, validate plans, record replacement relationships, protect lessons files, check activity, and perform constrained cleanup.
- **Instructions for Codex:** identify deliverables and dependencies from the current task context, write lessons, select authorized actions, and explain uncertainty.

Codex makes semantic judgments and writes lessons using available task evidence. The Python scripts do not automatically understand arbitrary documents, reconstruct chat context, or prove that every dependency has been identified.

## Features and boundaries

| Feature | Implemented behavior |
| --- | --- |
| Usage scanning | Read metadata and report logical bytes, allocated blocks, largest directories/files, and coverage |
| Growth comparison | Save signed baselines and compare complete, comparable scan scopes |
| Disposable workspaces | Create dedicated directories, record completion and retention declarations, and require a 24-hour cooling period |
| Cache maintenance | Use native pip, uv, npm, and pnpm commands with tool-specific checks |
| Historical revision discovery | Suggest candidates from names and version numbers within the same directory and format; never delete based on modification time |
| Revision tracking | Record tasks, artifacts, revisions, explicit replacement relationships, and multi-format delivery bundles |
| In-chat cleanup reminders | Offer a concrete scope after at least 3 successful deliveries of an artifact in the current chat and safely reclaimable predecessors; act after “yes” without repeating the same offer |
| Superseded-output cleanup | Remove only authorized, registered predecessors explicitly superseded by a valid final delivery |
| One lessons Markdown file | Bind one lessons path per task, update it in place, and protect it |
| Audit records | Persist intent before cleanup and record completed, skipped, failed, or partially completed actions |

**Not currently provided:** continuous monitoring, automatic cross-chat triggers, blanket historical-file cleanup, direct worktree deletion, chat/memory database compaction, system snapshot deletion, or global semantic deduplication.

## Installation

### Option 1: Ask Codex to install it

Give Codex the repository URL and request installation as a user skill:

```text
Install https://github.com/WUWengZheng/codex-disk-maintenance as a Codex skill.
```

### Option 2: Clone into your skills directory

```sh
skill_install_root="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skill_install_root"
git clone https://github.com/WUWengZheng/codex-disk-maintenance.git \
  "$skill_install_root/codex-disk-maintenance"
```

If the destination already exists, inspect its contents before replacing anything. Start a new chat and confirm the skill is available; you can also explicitly reference `SKILL.md` by its absolute path.

To use only the scripts, clone into a regular working directory instead. Installation into Codex is not required.

### Updating

If the installed Git checkout has no local changes:

```sh
git -C "${CODEX_HOME:-$HOME/.codex}/skills/codex-disk-maintenance" pull --ff-only
```

For a manually installed copy, compare and preserve local changes before switching to a Git-based installation. After updating, reload the skill in subsequent chats; an ongoing chat can explicitly be asked to read the updated `SKILL.md`.

## Managing repeated refinements

```text
Task: paper figure 6
v1.svg → v2.svg → v3.svg + v3.png (final delivery)
                         └── required dependencies: plot.py, assets/
```

The complete final bundle and its dependencies are retained. Only explicit predecessors of the final delivery become cleanup candidates.

- A trial or failed `v4` export does not automatically replace the delivered `v3`.
- Different formats may belong to the same bundle rather than replace each other.
- Independent, unreplaced alternatives and outputs from other tasks remain protected.
- Missing or changed final files/dependencies block cleanup of related predecessors.
- Without reliable replacement relationships, Codex checks current task evidence and asks which version is final when necessary. It does not simply retain the most recently modified file.

## Cleanup reminders after repeated deliveries

While managing iterations in the current chat, the skill registers one revision and its replacement relationships per successful delivery. SVG, PNG, and PDF files exported in the same round form one bundle, not multiple rounds. Drafts, tool retries, and failed exports do not count as successful deliveries.

By default, after at least **3 successful deliveries of an artifact in the current chat**, with explicit predecessor files that pass the checks, Codex offers cleanup at the end of a delivery. For example:

```text
Codex: Revision 3 is delivered. I found 2 intermediate files superseded by the final
       bundle (about 80 MiB). Keep final outputs, required sources, and the lessons
       file, and clean up these predecessors? Reply “yes” to proceed.
You:   Yes.
Codex: Updates the existing lessons file, rechecks the offered files and final
       bundle, performs eligible cleanup, and reports the actual result.
```

A reminder proposes an action; it does not delete in advance. File counts and sizes come from the actual candidate list. Sizes are estimates, not guaranteed disk-space recovery.

- Each chat has one current pending offer, which can include several artifacts from the same task. It is bound to actual files, final-delivery state, and that chat.
- The same final delivery and candidates are not repeatedly offered. Declined or expired offers do not produce repeated prompts; a new successful delivery with new candidates may produce another offer.
- A clear reply such as “yes,” “需要,” or “clean them up” authorizes deletion only when it directly answers the current concrete offer. The same words in another topic, a quotation, or a hypothetical do not trigger cleanup.
- Consent covers only the intermediates in that offer. It excludes other tasks, caches, worktrees, chats, and memory. Before execution, Codex updates and protects the task's one lessons Markdown file; if none is bound, it creates and binds `经验记录.md`.
- Offers expire after **24 hours**. Execution still rechecks the original candidates and final bundle. Expired, changed, or active files stop the affected cleanup without expanding the scope or increasing cleanup strength.
- Confirmation is used only once. Interruptions or partial failures are reported rather than retried automatically. Without reliable replacement relationships or safe candidates, reaching a round count does not justify a deletion offer.

This is an in-chat workflow while the skill is loaded, without a cross-chat listener. Historical revisions from other chats do not count toward this chat's deliveries. Normal automatic skill selection remains available; explicitly name `$codex-disk-maintenance` with the reminder request above to enable it for this task.

## One continuously updated lessons file

Task closeout follows this sequence:

1. Identify the final delivery bundle and its dependencies.
2. Read and update the existing task lessons file. For a new task, the default is `经验记录.md` in its output directory; an explicit user filename is honored.
3. Bind and protect the lessons file.
4. Clean up authorized predecessors that pass the checks.
5. Give a brief chat receipt with actual results and file locations.

The document contains evidence-backed conclusions, effective methods, reasons for failed approaches, useful commands, and a compact change record. Repeated observations are consolidated and superseded conclusions are marked. If the user explicitly requests exactly one lesson, maintain one principal lesson.

Future changes update the same file rather than create `经验记录_v2.md` or daily summaries. Separate tasks use their own directories and bindings. The lessons document is not a chat transcript and is not automatically imported into MemPalace or global memory.

The script binds and protects the file; Codex writes its content. Machine audit records still exist and are separate from the single human-readable lessons document.

## Command-line reference

Run these commands from the repository root. Replace `/absolute/...`, task names, and revision names with actual values.

### 1. Scanning and baselines

```sh
# Default scope: Codex data, related app directories, temp files, and tool caches
python3 scripts/disk_maintenance.py scan

# Restrict diagnostics to explicit roots; disable default roots and tool discovery
python3 scripts/disk_maintenance.py scan --root /absolute/task

# Add a project to the default scope and explicitly save a baseline
python3 scripts/disk_maintenance.py scan --project /absolute/project --save-baseline

# Focus on registered workspaces and native caches without increasing budgets
python3 scripts/disk_maintenance.py scan --candidates-only --save-baseline

# Compare the latest two saved baselines, or two explicit files
python3 scripts/disk_maintenance.py diff
python3 scripts/disk_maintenance.py diff /absolute/before.json /absolute/after.json
```

The default budget is 120 seconds and 500,000 filesystem entries. Exhausting the budget produces a partial report; incomplete coverage cannot establish deletion eligibility. A first scan cannot prove how much space grew today.

Scanning reads regular-file metadata rather than file contents. It does not follow symlinks and skips nested mounts and special files. Native location queries may generate incidental logs within the tools themselves.

### 2. Cleanup plans and execution

```sh
# Use the saved_path returned by scan
python3 scripts/disk_maintenance.py plan --scan /absolute/saved-scan.json

# Execute only authorized scopes; --ids can further restrict selected items
python3 scripts/disk_maintenance.py apply \
  --plan /absolute/saved-plan.json --authorize scratch pnpm
```

A scan used to create a plan must be no more than 15 minutes old; the plan also expires after 15 minutes. Targets and activity are checked again before execution. A rescan must respect the original authorization scope.

Whole-cache pip/npm eviction must be explicitly included:

```sh
python3 scripts/disk_maintenance.py plan \
  --scan /absolute/saved-scan.json --include-full-cache-clear
python3 scripts/disk_maintenance.py apply \
  --plan /absolute/saved-plan.json --authorize pip npm
```

This can increase future download or build costs. Total cache size is not a promise of reclaimed space.

### 3. Dedicated disposable workspaces

```sh
python3 scripts/disk_maintenance.py scratch create
# Store disposable intermediates in the returned workspace
python3 scripts/disk_maintenance.py scratch finish --run-id RUN_ID
# A keep declaration protects the entire workspace
python3 scripts/disk_maintenance.py scratch finish \
  --run-id RUN_ID --keep relative/result.pdf
```

Arbitrary historical directories cannot be registered as disposable workspaces. Active workspaces, those finished less than 24 hours ago, those containing keep declarations, and those still in use are ineligible.

### 4. Inspecting and tracking output revisions

```sh
python3 scripts/iterations.py inspect --root /absolute/task

python3 scripts/iterations.py track \
  --task paper --artifact figure6 --revision v1 --chat CHAT_ID --final \
  --file /absolute/figure6_v1.svg

python3 scripts/iterations.py track \
  --task paper --artifact figure6 --revision v2 --replaces v1 --chat CHAT_ID \
  --file /absolute/figure6_v2.svg --file /absolute/figure6_v2.png \
  --dependency /absolute/plot.py --dependency /absolute/assets --final

python3 scripts/iterations.py review
```

`--file`, `--dependency`, and `--replaces` can be repeated. Registered revisions are immutable; register a new revision after file edits. `--final` means an established delivery, not merely a filename containing `final`. Reminders count only successful deliveries associated with the current chat ID. When `--chat` is omitted, `CODEX_THREAD_ID` is used if set; historical revisions from another chat or without a chat binding do not count.

### 5. Binding lessons and pruning predecessors

Have Codex create or update the lessons file first, then bind it:

```sh
python3 scripts/iterations.py notes \
  --task paper --file /absolute/task/经验记录.md
```

Each task binds one path. Binding the same path again is allowed; switching to another path is refused. The lessons file can be updated in place: do not register it as an immutable revision or dependency snapshot. Cleanup stops if the bound document is missing.

The following command **deletes files**. Use it only after verifying final outputs, dependencies, and authorization:

```sh
python3 scripts/iterations.py prune \
  --task paper --artifact figure6 --authorize-superseded
```

It removes only explicit predecessor files. It does not empty the task directory or retain one “latest file” while deleting everything else. Revision pruning does not use the workspace's 24-hour rule; eligibility rests on explicit replacement relationships and a valid final delivery.

### 6. Creating, confirming, or dismissing a reminder

Use a stable `CHAT_ID` unique to the current chat, separate from other chats. `TASK` still identifies the current task. Codex checks for a reminder after each successful delivery. Continuing the two-round example above, register the third delivery:

```sh
python3 scripts/iterations.py track \
  --task paper --artifact figure6 --revision v3 --replaces v2 --chat CHAT_ID \
  --file /absolute/figure6_v3.svg --file /absolute/figure6_v3.png \
  --dependency /absolute/plot.py --dependency /absolute/assets --final

python3 scripts/iterations.py remind --task paper --chat CHAT_ID
```

When the result has `status: offered`, present its candidate scope, retained scope, file count, and size estimates. Use the returned `offer_id`, never an invented ID or one from another chat. Checking the same offer again does not repeat the prompt.

After the user directly accepts this offer, update and bind the single lessons file, then run:

```sh
# Deletes files: run only after the user explicitly accepts the current concrete offer
python3 scripts/iterations.py confirm \
  --chat CHAT_ID --offer-id OFFER_ID --authorize-superseded
```

If the user replies “not now,” record dismissal without deleting files:

```sh
python3 scripts/iterations.py dismiss --chat CHAT_ID --offer-id OFFER_ID
```

Offer expiry, file revalidation, and one-time confirmation are separate from disposable-workspace cooling periods. Ordinary `prune` remains available for directly authorized cleanup without waiting for three rounds. A reminder does not grant cache-cleanup permission.

## Cache adapters

| Tool | Native operation | Conditions |
| --- | --- | --- |
| uv | `uv cache prune` | Skipped by default while historical symlink dependencies are unverified |
| pnpm | `pnpm store prune` | Check store activity and related processes |
| pip | `pip cache purge` | Separate authorization for whole-cache eviction |
| npm | `npm cache clean --force` | Separate authorization for whole-cache eviction |

Only conventional cache locations listed in the implementation are supported. Custom locations are diagnostic-only. Missing tools are not installed. Node processes conservatively block npm/pnpm cleanup.

Only after an operator establishes that no retained environment depends on cache symlinks may they provide `DISK_MAINTENANCE_UV_NO_SYMLINK_DEPENDENCIES=1` for that invocation. The skill does not set this assertion automatically to bypass a check.

See [cleanup rules](references/cleanup-rules.md) for paths, minimum versions, and parameters.

## Data protection, state, and recovery

Default state directory:

```text
${CODEX_HOME:-~/.codex}/disk-maintenance/
├── signing.key             Local signing key
├── registry.json           Disposable-workspace registry
├── outputs-registry.json   Output revisions, lessons bindings, and cleanup offers
├── scan-*.json             Usage baselines
├── plan-*.json             Cleanup plans
└── result-*.json           Audit records
```

- The main script supports global `--codex-home` and `--state-dir` before the subcommand. The revision script supports `--state-dir`.
- `CODEX_HOME` defaults to `~/.codex`. The state directory must be user-owned with mode `0700`.
- HMAC detects changes to signed plans and registries; it does not isolate them from a malicious program controlling the same user account.
- Keep at most 30 usage snapshots and 20 MiB of total state. Signing keys and workspace/output registries are not automatically rotated; excessive essential metadata blocks new writes.
- Worktrees, chats, memory databases, credentials, skills, runtimes, final deliverables, and required dependencies are protected by default. Unknown historical files are not deleted based on age or names.
- Before deletion, check coverage, identity, activity, and audit persistence. Maintenance uses a single-instance lock.
- Disposable workspaces are renamed on the same filesystem and checked again. Superseded outputs also use same-directory temporary renames and identity checks. Cleanup does not make a large backup copy or count moving files to Trash as reclaimed space.
- Interruptions can leave partial results. Inspect original and quarantine paths in the audit record, preserve remaining files, and do not automatically retry deletion or overwrite a recreated original path.
- The scripts do not remove system snapshots, terminate existing user processes, or maintain databases. Timeouts affect only a child command started by the current invocation.

Scripts emit typed JSON. Exit code `2` indicates a top-level refusal or error. Exit code `0` can still include skipped, failed, or partially completed items; inspect individual statuses.

Logical size, allocated blocks, and filesystem available space are different measurements. APFS clones, hardlinks, snapshots, and concurrent writers affect the results. Removed file size is not automatically equal to space physically reclaimed.

## Testing and validation

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Tests use isolated directories and simulated package managers. They cover usage and growth, symlinks and hardlinks, scan budgets, plan tampering, changed files, activity checks, disk-full errors, command failures, final-output protection, replacement relationships, single-file lessons bindings, reminder deduplication, chat isolation, expiry, and revalidation at confirmation.

Skill formatting can be checked with Codex's bundled `skill-creator/scripts/quick_validate.py`. That development validator needs PyYAML; core scripts and unit tests still use only the standard library.

## Repository layout

```text
codex-disk-maintenance/
├── README.md                 Chinese documentation
├── README.en.md              English documentation
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── disk_maintenance.py
│   └── iterations.py
├── references/
│   ├── cleanup-rules.md
│   └── iteration-results.md
└── tests/
    ├── test_disk_maintenance.py
    ├── test_iterations.py
    └── test_reminders.py
```

## Frequently asked questions

**Does installation enable automatic daily deletion?**

No. Scheduled jobs, session hooks, and background monitoring are not implemented or configured.

**Why did no reminder appear?**

Confirm that the updated skill is loaded in this chat and managing the current iterations. One artifact needs at least three successful deliveries in this chat and safe candidates; many chat messages, many files, or old files alone are insufficient. The same offer is not repeatedly prompted, and the skill does not listen to other chats.

**Does replying “yes” delete every cache and old file?**

No. It authorizes only the concrete offer just shown in the current chat. Final outputs, required dependencies, and the one lessons file remain protected. Changed candidates, expired offers, or failed checks prevent deletion under the old offer.

**Can it automatically classify any old result as unnecessary?**

No. Historical filename inspection offers hints only. Reliable pruning needs current task evidence, explicit replacement relationships, and a valid final delivery.

**Does “one Markdown file” mean all other deliverables are deleted?**

No. It refers to the number of lessons documents. Final documents, images, editable files, and required assets are retained.

**Are lessons automatically stored in MemPalace?**

No. Lessons stay in the task's bound Markdown file and are not automatically imported into global memory.

**Can it guarantee a fixed amount of reclaimed space?**

No. It reports observed changes and why candidates could not be reclaimed.

**How do I report a problem?**

Use [Issues](https://github.com/WUWengZheng/codex-disk-maintenance/issues) and include the command, OS/Python versions, sanitized output, and expected behavior. Do not upload raw chats, scan reports, signing keys, or private deliverables.

## Contributing

When changing scripts, verify behavior and data-protection boundaries. New cache adapters should supply native commands, explicit target bindings, and isolated tests. New automation should explain its triggers, authorization, retention rules, and failure handling.

See [SKILL.md](SKILL.md), [cleanup rules](references/cleanup-rules.md), and [output revision rules](references/iteration-results.md) for implementation constraints.
