# Keep the delivered revision, reclaim superseded outputs

When a user iterates on one result, organize revisions by task and artifact,
not by an entire day or file extension. One artifact may have a final bundle:
editable source + PDF + PNG + required assets. Protect the entire delivered
bundle and its declared dependencies. Unrelated drafts/branches remain protected.

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
`--replaces` must name an already registered revision of the same artifact.
Use a new revision after any file edits. Keep outputs at distinct paths if
historical versions need tracking; overwritten files cannot be recovered.

```sh
python3 "$SKILL_DIR/scripts/iterations.py" track --task paper --artifact figure6 --revision v1 --file /absolute/figure6_v1.svg
python3 "$SKILL_DIR/scripts/iterations.py" track --task paper --artifact figure6 --revision v2 --replaces v1 --file /absolute/figure6_v2.svg --file /absolute/figure6_v2.png --dependency /absolute/plot.py --dependency /absolute/assets --final
python3 "$SKILL_DIR/scripts/iterations.py" review
```

Only use `--final` when the new export succeeded and current user/task context
establishes it is the delivered result. A filename containing 'final' is not
acceptance evidence. If continuing optimization with a trial, leave it as a
draft until delivered. A failed/newer draft never displaces the accepted final.
Declare all known dependencies, including sources from older revisions; do not
claim arbitrary HTML/SVG/PDF/Office dependency graphs were automatically parsed.
If dependencies are unknown, finish that review before authorizing deletion.

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
