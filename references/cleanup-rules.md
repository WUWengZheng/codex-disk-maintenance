# Cleanup contracts and failure handling

## Boundaries and accounting

- Target: macOS, Python >=3.9. `lsof` and `ps` are required for deletion checks.
  Missing tools are reported, never installed. Linux is not the validated
  delivery target; Windows deletion is unsupported.
- Discover `CODEX_HOME`, Codex app data/caches, Codex runtimes, system temp,
  native cache locations and explicitly named projects. Scan metadata only;
  reject symlink path components and skip nested mounts. Default bounds:
  120 seconds including discovery, 500,000 entries, 30 largest files, 1,000
  disjoint top-level units. Missing/incomplete roots are not treated as empty.
- Protect worktrees, chats, SQLite/WAL/SHM, attachments, credentials, configs,
  plugins including `plugins/cache`, runtimes, environments, browser profiles,
  images and visualizations. Old unknown temp and app caches are report-only.
- Root summaries overlap and cannot be summed. Hardlinks are counted once per
  scan. APFS clones/snapshots mean allocated blocks are not exclusive physical
  bytes. Diffs exclude incomplete coverage and changed root sets because inode
  attribution may move. Diffs establish correlation, not task causation.
- Emergency is available space <5 GiB OR <5% of the volume. Prioritize known
  candidates but keep checks. No large backup copies or Trash moves. If audit
  writes fail, stop before mutation. Partial I/O failures remain partial results.

## State, interfaces and authorization

State defaults to `CODEX_HOME/disk-maintenance`, user-owned with mode 0700.
HMAC signatures bind saved scans/plans and the registry to a private key. This
is tamper detection, not protection from a hostile user controlling the account.
JSON input is bounded to 8 MiB. Read-only verification cannot create a key.
Changing state directory does not make old plans trustworthy.

`scan --save-baseline` returns signed JSON and `saved_path`. `plan --scan PATH`
checks that signature and a 15-minute age. Plan items contain scope, path,
fixed action, identity/tree fingerprint, evidence, impact and size upper bound;
plans expire in 15 minutes. `apply --authorize SCOPE... [--ids ID...]` limits
execution, but does not establish human intent: the invoking agent must preserve
the user's actual authorization. Pip/npm bulk actions additionally require
`plan --include-full-cache-clear`. Plans cannot supply arbitrary commands.

One nonblocking flock protects maintenance writes and cleanup. Before mutation,
persist an audit record and reserve metadata headroom. Retain <=30 snapshots,
<=20 MiB total metadata, rotating oldest scan/plan/result records. Registry/key
are never rotated; excessive essential metadata blocks writes. Disposable
workspace contents are separate from this metadata budget.

Outputs have `version: 1` and kind `scan`, `diff`, `plan`, `result`, `scratch`,
or `error`. Exit 2 is refusal/top-level failure. Apply can exit 0 with skipped or
failed items: inspect statuses. Reports never store file contents, raw process
arguments or raw tool stderr.

## Scratch lifecycle

Scratch lives at `CODEX_HOME/tmp/disk-maintenance/<random-id>`. Only `scratch
create` can create the directory and signed inode-bound registry record.
`scratch finish` marks the task done; every keep declaration preserves the
whole tree. Eligible runs are explicitly disposable, finished >=24h, contain no
declared artifacts or symlinks/hardlinks, and have complete matching scans.

Before deletion, lsof must conclusively show no open files/working directory;
errors/truncation block it. Re-measure after activity checks. Persist intent,
rename within the same parent, then inspect activity and full fingerprint again.
Failed checks restore the name if vacant; otherwise retain quarantine.

Removal uses directory descriptors/no-follow opens and measured entry
identities. Each file is renamed to a random name, validated and unlinked.
New arrivals are not swept; nonempty directories remain. Mid-removal failure
stops the batch, reports possibly partial completion, and retains the quarantine
pointer. Registry states `quarantining`, `deleting`, and
`quarantined_review_required` require inspection of original and quarantine
paths. Do not auto-reset or auto-resume; preserve remaining files and explain
recovery paths. Activity checks cannot prove a task will never reopen a file;
mark finished only after consumers end. This addresses normal races, not a
hostile same-user writer racing every operation.

## Native caches

Probe user/global cache paths from neutral cwd `/`; disable Corepack network
downloads and pnpm version management. Never invoke install/update/project
scripts. Bind resolved executable identity/version and actual cache location.
Minimum versions: uv 0.4, pip 20.1, npm 6, pnpm 8. Unknown/older versions fail
closed. Unsupported maintenance commands are failures; no direct-delete fallback.

| Tool | Conventional roots | Fixed action |
| --- | --- | --- |
| pip | `~/Library/Caches/pip`, `$XDG_CACHE_HOME/pip` | `pip3 --cache-dir ROOT cache purge` |
| uv | `$XDG_CACHE_HOME/uv`, `~/Library/Caches/uv` | `uv cache prune --cache-dir ROOT` |
| npm | `~/.npm`, `$XDG_CACHE_HOME/npm`, `~/Library/Caches/npm` | `npm --cache ROOT cache clean --force` |
| pnpm | `~/Library/pnpm/store`, `~/.local/share/pnpm/store`, `~/Library/Caches/pnpm`, `$XDG_CACHE_HOME/pnpm/store`, including versioned descendants | `pnpm --store-dir ROOT store prune` |

XDG defaults to `~/.cache`. Other/custom locations are report-only. Any cache
overlapping Codex, runtimes, application support or explicit projects is refused.
Shared caches are not exclusively Codex data. Size is an upper bound, not an
exact deletion preview; native commands may lack dry-run support.

Rediscover bindings, re-measure and inspect open files/package-manager processes
before each action. Conservatively block npm/pnpm if Node is running. Process
inventory failure/truncation blocks cleanup. Commands use a 60-second timeout
and a 1-MiB streaming output limit, retaining <=64 KiB in memory, not reports.
Timeout or nonzero exit is possibly partial and stops the batch. Only this
invocation's child command is terminated; existing processes are not stopped.

uv is blocked with `uv_symlink_dependency_safety_unverified` by default.
Historical symlink-mode environments cannot be proved independent by today's
default or `UV_LINK_MODE`. Only after the human operator establishes that no
retained environment depends on this cache via symlinks may they supply
`DISK_MAINTENANCE_UV_NO_SYMLINK_DEPENDENCIES=1`. Never set it automatically.
It is a trust assertion, not a scanner-generated guarantee.

Primary references:

- [uv cache safety](https://docs.astral.sh/uv/concepts/cache/)
- [uv symlink mode](https://docs.astral.sh/uv/reference/cli/)
- [pip cache](https://pip.pypa.io/en/stable/cli/pip_cache/)
- [npm cache](https://docs.npmjs.com/cli/v11/commands/npm-cache/)
- [pnpm store](https://pnpm.io/cli/store)

## Verification and recurrence

Report logical/allocated reductions separately from observed available-space
changes. Concurrent writers/shared extents mean free-space deltas are not
exclusive attribution. If a completed action shows no improvement, read-only
`lsof +L1` and `tmutil listlocalsnapshots` provide clues; do not terminate holders
or remove snapshots. No scheduler, hook or background service is installed.
Worktree recycling is outside v1 mutation scope.

Run `python3 -m unittest discover -s tests -v` from this skill directory, plus
skill-creator's `quick_validate.py`. Tests restrict discovery to isolated temp
fixtures and simulated CLIs; never evict real caches. Host smoke tests use
`scan --root` on a small known source directory without saving state or applying.
