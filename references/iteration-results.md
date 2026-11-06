# Keep the delivered revision, reclaim superseded outputs

When a user iterates on one result, organize revisions by task and artifact,
not by an entire day or file extension. One artifact may have a final bundle:
editable source + PDF + PNG + required assets. Protect the entire delivered
bundle and its declared dependencies. Unrelated drafts/branches remain protected.

## Evidence of refinement, not unrelated content

Cleanup edges require refinements of the same original result with the same
purpose and content scope. Establish this from the current request and actual
editing lineage. Correcting the prior figure's labels/layout or the prior report's
wording/error qualifies even when file bytes change. A new subject, different
data/time scope, independent alternative, or uncertain relation stays separate
and protected. Name/mtime/format/text-similarity hints do not establish identity.

Use `--improves REV --improvement-evidence 'brief concrete edit basis'`; repeat
`--improves` for multiple established parents. It implies the corresponding
`--replaces` entries. The evidence is required, nonempty and at most 1000
characters; keep it factual and short, without copying private content/transcripts.
The executor verifies declared edges/evidence, not arbitrary semantic identity.
Never manufacture a basis just to obtain deletion eligibility. Unknowns stay kept.

Only evidenced improvement edges are traversed, for review, reminders and pruning.
Legacy `--replaces` alone remains a stored relation but does not permit cleanup.
Do not rewrite signed/immutable history to retrofit evidence. If a current-task
refinement is established, register a new revision with its real parents.
In-place edits without a distinct old output have nothing separate to remove;
do not create extra copies solely to populate this registry.

For explicitly enabled defaults, see [default-reminders.md](default-reminders.md).

## Proactive reminder and short confirmation

While this skill is active for the current task, track one revision per successful
**delivery round**, with `--final --chat CHAT_ID`. Bundle all delivered formats
in that revision and declare evidenced improvement predecessors and dependencies. Do not
count tool retries, failed exports, draft-only versions, or plain conversation.
`--chat` defaults to `CODEX_THREAD_ID` for track when available. Use one stable
current-chat ID and task ID; never invent historical chat associations.

After each delivery, check:

```sh
python3 "$SKILL_DIR/scripts/iterations.py" remind --task TASK --chat CHAT_ID
```

The default threshold is three delivered revisions along one evidenced improvement chain in this chat,
with a current valid final and at least one eligible explicit predecessor. Old
registrations without chat/delivery evidence do not count. The same preflight
as pruning rejects active files, incomplete/changed bundles and protected roots.
A read-only inspection request does not authorize registering revisions or offers.

Only `status: offered` warrants a prompt. The signed registry persists one
pending offer per chat, with an `offer_id`, exact candidate snapshots, retained
final bundle, count, logical/allocated upper estimates, and a 24-hour expiration.
Ask once about the concrete scope, preferably via an available asynchronous
question tool. Example: 「已完成多轮优化，发现 N 个被最终版替代的中间文件（约 X）。
保留最终成果、必要源文件和经验记录，需要清理吗？回复『需要』即可。」
Use actual returned numbers; estimates do not promise physical freed space.
Do not repeat the same delivery's suggestion after dismissal, expiration, or
no answer. A newly delivered final can produce a new suggestion.

A clear direct affirmative reply to the pending proposal grants its scope only.
Unrelated 「需要」, hypothetical/quoted wording and cross-chat replies never count.
The agent establishes this conversational consent; the CLI does not parse natural
language or prove consent just because a flag was passed. It cannot remind when
the agent never loads or runs the skill, and installs no scheduler or global hook.

After consent, update the single task lessons document and bind it using `notes`
(the closeout steps below). Then:

```sh
python3 "$SKILL_DIR/scripts/iterations.py" confirm --chat CHAT_ID --offer-id OFFER_ID --authorize-superseded
```

Confirmation requires the bound MD to exist, rechecks the original exact scope
and active files, consumes the offer before deletion, and runs the ordinary
pruner with another scope check. It cannot add new artifacts, files, caches or
tasks to the approval. Changed/expired offers require a newly presented scope
and new consent through the ordinary review/prune workflow. Partial or interrupted
execution stays consumed: inspect journals; never silently replay it.

For a negative reply:

```sh
python3 "$SKILL_DIR/scripts/iterations.py" dismiss --chat CHAT_ID --offer-id OFFER_ID
```

No answer means no deletion. Summarize actual removals/skips and directory bytes
separately from observed volume-space changes. Preserve finals, sources, declared
dependencies, the sole lessons MD, chat history and memory.

## Single Markdown task closeout

Recognize a request such as 「整理这次对话的结果，删除不必要结果，把过程经验总结在一个
MD 文件里，后续修改也写回这个文件」 as task-scoped closeout. A hypothetical
「如果我说……」 configures/explains the workflow; it does not initiate real deletion.

1. Identify the current task's final deliverables, sources/dependencies and
   explicit predecessor relationships from available conversation context.
   Use existing records and current task evidence; do not mine chat archives.
   Keep unrelated results and uncertain versions; explain unresolved items.
2. Reuse the task's bound notes path. For an unbound task, reuse an existing
   task-specific experience MD if unambiguous; otherwise create `经验记录.md`
   inside that task's output directory. Separate tasks use their own directory.
   Honor an explicit user filename. Read the existing document before editing.
3. Write/update only this one lessons document: current final artifact paths,
   useful confirmed lessons, failed approaches with reasons, reproducible
   commands/settings when helpful, and a compact dated change record. Keep it
   concise; consolidate repeated observations and mark superseded advice.
   If the user explicitly requests exactly one lesson, retain one principal
   lesson and revise it. Otherwise use one document for the relevant lessons.
   Do not invent lessons or dump the transcript. Preserve unrelated/user text.
4. Bind the successfully saved document before pruning:

   ```sh
   python3 "$SKILL_DIR/scripts/iterations.py" notes --task TASK --file /absolute/task/经验记录.md
   ```

   The binding is private signed metadata, not a second human-facing summary.
   It fixes one path per task and protects it from version pruning. The notes
   file is mutable: do not register it as an immutable output revision or
   dependency snapshot. Updating it in place must not block normal cleanup.
5. Perform authorized version pruning with the ordinary checks. The phrase
   authorizes only clearly superseded results of this task, not deleting all
   files other than the MD. Preserve final deliverables and necessary sources.
   Do not create separate lessons reports, `v2.md`, dated summary copies, or
   automatic MemPalace/global-memory records. Machine audit records still apply.
6. Give a short chat receipt linking the final artifacts and the sole MD,
   with actual cleanup/skipped results. Subsequent refinements update the same
   MD, consolidate the current conclusions and add only meaningful dated changes.

The script binds/protects the MD; the agent authors its content from task
evidence. Installation alone does not run this workflow or gather experience.

## Existing files: inspect first

```sh
python3 "$SKILL_DIR/scripts/iterations.py" inspect --root /absolute/task
```

This bounded, read-only metadata scan groups names such as `report_v1.pdf` and
`report_v2.pdf`, within the same directory and format. It suggests the highest
explicit version when unambiguous; it never authorizes deletion. Ambiguous
unversioned/final names, equal version numbers, unrelated directories, failed
exports, different formats and mere modification time cannot establish the
accepted result. Describe uncertainty, ask the user to identify the intended
delivered result only when current task evidence is insufficient. Do not read
conversation archives to reconstruct relationships. Missing filename patterns
are not evidence that a file is final or disposable.

## Future iterations: record explicit replacement relationships

Register successful exports as they are generated. `--revision` is immutable;
`--improves` must name an already registered revision of the same artifact with
a concrete basis for refinement of that same deliverable.
Use a new revision after any file edits. Keep outputs at distinct paths if
historical versions need tracking; overwritten files cannot be recovered.

```sh
python3 "$SKILL_DIR/scripts/iterations.py" track --task paper --artifact figure6 --revision v1 --file /absolute/figure6_v1.svg
python3 "$SKILL_DIR/scripts/iterations.py" track --task paper --artifact figure6 --revision v2 --improves v1 --improvement-evidence 'Correct labels and contrast in the previous figure, keeping its data scope' --file /absolute/figure6_v2.svg --file /absolute/figure6_v2.png --dependency /absolute/plot.py --dependency /absolute/assets --final
python3 "$SKILL_DIR/scripts/iterations.py" review
```

Only use `--final` when the new export succeeded and current user/task context
establishes it is the delivered result. A filename containing 'final' is not
acceptance evidence. If continuing optimization with a trial, leave it as a
draft until delivered. A failed/newer draft never displaces the accepted final.
Declare all known dependencies, including sources from older revisions; do not
claim arbitrary HTML/SVG/PDF/Office dependency graphs were automatically parsed.
If dependencies are unknown, finish that review before authorizing deletion.

Do not combine different content or independent alternatives into one improvement
chain, even when they were generated in the same conversation or share names.
Only final plus its evidenced improvement ancestors count toward reminder rounds.

The private signed `outputs-registry.json` is essential metadata and is not
rotated. It is separate from chat history/memory. Every declared dependency,
all unreplaced branches, and all current finals across tasks remain protected.
Review checks recorded metadata fingerprints: missing/changed final files or
assets block predecessors. A later edit to an old output protects that file.
Directory dependencies protect their full subtree. Shared paths/inodes are
protected; no fuzzy or semantic duplicate deletion is performed.

## Prune only explicit predecessors

After user authorization for the concrete artifact's superseded outputs:

```sh
python3 "$SKILL_DIR/scripts/iterations.py" prune --task paper --artifact figure6 --authorize-superseded
```

This freshly verifies the signed registry, retained bundles and candidates,
checks activity, and writes an audit intent before deleting individual files.
It uses same-parent temporary renames and identity validation, never a directory
sweep. Changed/in-use objects or audit failures stop the operation. No cooling
period applies here: explicit predecessor relationships and final delivery
evidence replace the scratch workspace's age rule. The agent must establish
dependency completeness before invoking prune; the flag is not evidence of
human authorization. This skill upgrade itself does not authorize pruning real
files, and no scheduler is installed.

Chat/memory databases, Codex-managed data, runtimes and working-state locations
are not valid pruning targets. On interruption inspect the result journal's
original/quarantine paths; do not automatically resume or overwrite a recreated
original path. Volume before/after readings are observations, not guaranteed
physical reclaimed bytes; renaming alone reclaims no space.
