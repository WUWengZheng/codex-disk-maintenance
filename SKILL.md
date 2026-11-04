---
name: codex-disk-maintenance
description: Diagnose Codex disk usage, identify iterative output versions, retain final deliverables and dependencies, and reclaim explicitly superseded outputs or managed caches. Also use for conversation/task closeout with one continuously updated Markdown lessons file. Runs on demand.
---

# Codex 磁盘维护

Use the bundled Python 3.9+ standard-library CLI. Set `SKILL_DIR` to the directory
containing this file; do not assume the source and installed paths are the same.
Commands emit JSON; explain findings in the user's language.

## 一句话入口

用户说「这次只保留最终结果，清理中间版本」时，启用当前任务的迭代成果管理。
同义表达如「只留最后一版」也适用。无需用户提供 CLI 命令、版本号或重复调用。
按 [iteration-results.md](references/iteration-results.md) 在每次成功交付时自动登记独立版本、
替代关系及依赖，保留最近一次成功交付的完整成果；试验稿和失败导出不替代定稿。
该句中的「清理」授权回收本次任务明确被替代的已登记版本，执行前仍需完成所有复核。
仅说「只留最后一版」表达保留偏好，不扩展为删除历史文件的授权。
既有文件关系不明时先识别并呈现候选；只询问无法从当前任务确定的最终版。
此入口作用于当前任务，按需执行，不安装后台触发器，不影响其他项目、聊天或记忆。

用户说「把这次对话中的结果整理一下，删除不必要的结果，总结过程经验到一个 MD，
后续修改也记录在这个 MD」或同义表达时，执行任务收尾：
按 [iteration-results.md](references/iteration-results.md#single-markdown-task-closeout)
先维护当前任务唯一的经验文件并将其绑定保护，再核对最终成果、清理明确被替代的版本。
使用当前对话已有上下文，不遍历聊天档案。不把这条示例或假设当成当下删除授权。

## Choose the authorized workflow

- **Inspect:** metadata scan and explanation only. Do not apply, archive chats,
  change settings, or stop processes.
- **Compare:** save a baseline as part of authorized maintenance; compare two
  saved scans. A first scan proves occupancy, not a daily growth rate or cause.
- **Clean:** prepare concrete candidate scopes and impacts, then apply only
  the scopes already authorized. If authorization is missing, ask once about
  the concrete list. Do not repeat an existing authorization or ask per file.
  Implementing/testing this skill does not authorize real-data cleanup.
- **Emergency:** prioritize registered scratch and known caches, retain every
  check, and print findings even if no baseline can be saved.

Read [cleanup-rules.md](references/cleanup-rules.md) before planning or applying
cleanup. Never bypass a refusal with `rm`, edited signatures/registry records,
weaker checks, or elevated privileges. Do not mine conversation archives.

## Inspect and compare

```sh
python3 "$SKILL_DIR/scripts/disk_maintenance.py" scan --seconds 120 --max-entries 500000
python3 "$SKILL_DIR/scripts/disk_maintenance.py" scan --project /absolute/project --save-baseline
python3 "$SKILL_DIR/scripts/disk_maintenance.py" diff
python3 "$SKILL_DIR/scripts/disk_maintenance.py" diff /absolute/before.json /absolute/after.json
```

`--root /absolute/path` replaces default roots and disables tool discovery;
repeat for a bounded diagnostic or installation smoke test. Do not default to
`/` or the entire home directory. `--project` adds a project to normal discovery.
Global overrides `--codex-home PATH` and `--state-dir PATH` go **before** the
subcommand. `CODEX_HOME` is honored, otherwise use `~/.codex`. A read-only scan
does not create this skill's state. `--save-baseline` persists metadata.
Native tools may perform incidental logging during location queries; no tool
installation/update commands are invoked.

If broad coverage exhausts its budget, focus a new scan with
`scan --candidates-only --save-baseline` on registered scratch and discovered
caches. It keeps the same limits and does not establish coverage of other data.

Explain largest directory units, protected data, rebuildable caches, uncertain
ownership and incomplete coverage. `coverage` roots can overlap; do not sum
them. `units` are disjoint top-level units with inode-attributed bytes; when
`units_truncated` is true the list is not exhaustive. Hardlinks are counted once
across the scan. APFS shared extents prevent promised physical reclamation.
Do not read credentials, chat content or database contents for ownership.

## Plan and apply

Use the returned `saved_path`, not a guessed filename:

```sh
python3 "$SKILL_DIR/scripts/disk_maintenance.py" plan --scan /absolute/saved-scan.json
python3 "$SKILL_DIR/scripts/disk_maintenance.py" apply --plan /absolute/saved-plan.json --authorize scratch uv pnpm
```

Pip/npm whole-cache eviction requires its own explicit scope and explanation
of redownload/build costs:

```sh
python3 "$SKILL_DIR/scripts/disk_maintenance.py" plan --scan /absolute/saved-scan.json --include-full-cache-clear
python3 "$SKILL_DIR/scripts/disk_maintenance.py" apply --plan /absolute/saved-plan.json --authorize pip npm
```

`--ids` additionally selects item IDs. Plans and source scans expire after 15
minutes. Re-scan expired/changed targets; do not silently expand authorized
scopes. Unknown historical temporary directories are diagnostic-only. Custom
cache locations outside supported conventional roots are diagnostic-only.
The uv adapter refuses cleanup unless the operator established that no retained
environment depends on cache symlinks; see the reference. Never invent that
attestation to make a candidate pass.

After apply, report completed/skipped/failed items, target size reductions, and
observed filesystem free-space changes separately. A successful command does
not prove the disk issue is resolved. Returned deleted-file/snapshot diagnostics
are clues, not exclusive explanations. Never delete snapshots or kill holders.
Report retained quarantine paths after interrupted scratch removal; do not
automatically resume a deletion or reset an interrupted registry state.
Files still in quarantine count as retained occupancy, not reclaimed space.

## Prevent repeat accumulation

For repeated optimization of the same deliverable, use
[iteration-results.md](references/iteration-results.md). It covers read-only
version discovery, explicit predecessor tracking, final multi-format bundles,
dependency preservation and authorized pruning. A request to identify versions
does not authorize deleting existing results. Do not mine historical chats to
infer version relationships. Preserve chat/memory data throughout.

For future tasks needing disposable intermediate files:

```sh
python3 "$SKILL_DIR/scripts/disk_maintenance.py" scratch create
python3 "$SKILL_DIR/scripts/disk_maintenance.py" scratch finish --run-id RUN_ID
python3 "$SKILL_DIR/scripts/disk_maintenance.py" scratch finish --run-id RUN_ID --keep relative/result.pdf
```

Creation makes a new private workspace; arbitrary existing directories cannot
be registered. Store final deliverables outside it. If a deliverable remains
inside, `--keep` preserves the **entire workspace**. Mark finished only when all
consumers are done; unfinished workspaces remain protected. Finished workspaces
cool for 24 hours and still require activity/identity checks.

Use later baseline comparisons to recommend dependency reuse, reduced repeated
rendering/recording, and scratch workspaces. Do not globally disable caches or
edit projects without authorization. This skill runs on demand and does not
add hooks, schedulers, background services, or global rules.
