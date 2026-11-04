#!/usr/bin/env python3
"""Inspect revision families; explicitly track delivered bundles and prune predecessors."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

import disk_maintenance as dm

REGISTRY = "outputs-registry.json"
PATTERN = re.compile(r"(?:[ _.-]+(?:v|rev|r)(\d+)|[ _.-]*(?:版本)(\d+)|[ _.-]+(final|finalized|最终版|终稿|定稿))$", re.I)


def inspect(root, seconds=120, max_entries=500000):
    root = dm.no_links(root)
    scanner = dm.Scanner(seconds=seconds, max_entries=max_entries)
    measured = scanner.measure(root)
    groups = {}
    for path, item in scanner.nodes.items():
        if not item.get("identity") or item["identity"][2] != stat.S_IFREG:
            continue
        p = Path(path)
        stem, number, final = p.stem, None, False
        while True:
            match = PATTERN.search(stem)
            if not match:
                break
            if match[1] or match[2]:
                number = int(match[1] or match[2])
            final = final or bool(match[3])
            stem = stem[:match.start()]
        if not stem:
            continue
        key = (str(p.parent), stem.casefold(), p.suffix.lower())
        groups.setdefault(key, []).append({"path": path, "revision_hint": number,
            "final_name_hint": final, "logical_bytes": item["logical_bytes"],
            "mtime": item.get("newest_mtime"), "unversioned": number is None and not final})
    families = []
    for key, files in sorted(groups.items()):
        if len(files) < 2 or not any(f["revision_hint"] is not None or f["final_name_hint"] for f in files):
            continue
        suggested = None
        if not any(f["unversioned"] for f in files):
            finals = [f for f in files if f["final_name_hint"]]
            numbers = [f["revision_hint"] for f in files if f["revision_hint"] is not None]
            if len(finals) == 1 and (not numbers or (finals[0]["revision_hint"] is not None and finals[0]["revision_hint"] == max(numbers))):
                suggested = finals[0]["path"]
            elif not finals and numbers:
                newest = [f for f in files if f["revision_hint"] == max(numbers)]
                if len(newest) == 1:
                    suggested = newest[0]["path"]
        families.append({"directory": key[0], "artifact_hint": key[1], "format": key[2],
                         "files": files, "suggested_latest": suggested,
                         "status": "needs_confirmation", "deletion_authorized": False})
    return {"version": 1, "kind": "iteration_inspection", "complete": measured["complete"],
            "errors": measured["errors"], "entries_examined": scanner.count, "families": families,
            "note": "Filename hints only. No content, history, or dependencies inferred; never auto-delete these suggestions."}


def load(store):
    path = store.root / REGISTRY
    if not path.exists():
        return {"version": 1, "kind": "output_registry", "groups": {}}
    registry = dm.read_json(path)
    store.verify(registry, "output_registry")
    return registry


def group_key(task, artifact):
    if not task.strip() or not artifact.strip() or len(task) > 200 or len(artifact) > 200:
        raise dm.Refusal("task_and_artifact_required_max_200_chars")
    return json.dumps([task, artifact], ensure_ascii=True)


def bind_notes(store, task, path):
    """Remember one mutable lessons document per task, outside revision snapshots."""
    group_key(task, 'notes')
    path = dm.no_links(path)
    if path.suffix.lower() != '.md' or not path.is_file():
        raise dm.Refusal('existing_markdown_notes_required')
    with store.lock():
        registry = load(store)
        notes = registry.setdefault('notes', {})
        if task in notes and notes[task] != str(path):
            raise dm.Refusal('task_notes_path_already_bound_update_existing_file')
        notes[task] = str(path)
        store.write(REGISTRY, store.sign(registry))
    return {'version':1,'kind':'task_notes','task':task,'path':str(path),'mode':'update_in_place'}


def snapshot(path, dependency=False):
    path = dm.no_links(path)
    info = path.stat()
    if not (stat.S_ISREG(info.st_mode) or (dependency and stat.S_ISDIR(info.st_mode))):
        raise dm.Refusal("outputs_must_be_regular_files")
    measured = dm.local_measure(path)
    if not measured["complete"] or measured.get("links"):
        raise dm.Refusal("incomplete_or_linked_bundle")
    return {"path": str(path), "measurement": measured}


def track(store, task, artifact, revision, files, dependencies=(), replaces=(), final=False):
    if not revision.strip() or len(revision) > 128 or not files:
        raise dm.Refusal("revision_and_output_files_required")
    with store.lock():
        registry = load(store)
        key = group_key(task, artifact)
        group = registry["groups"].setdefault(key, {"task": task, "artifact": artifact, "revisions": {}, "final": None})
        if revision in group["revisions"]:
            raise dm.Refusal("revision_immutable_register_a_new_revision")
        if set(replaces) - set(group["revisions"]):
            raise dm.Refusal("unknown_predecessor")
        outputs = [snapshot(p) for p in dict.fromkeys(files)]
        deps = [snapshot(p, dependency=True) for p in dict.fromkeys(dependencies)]
        group["revisions"][revision] = {"files": outputs, "dependencies": deps,
            "replaces": list(dict.fromkeys(replaces)), "created_at": dm.utc()}
        if final:
            group["final"] = revision
        store.write(REGISTRY, store.sign(registry))
        return {"version": 1, "kind": "iteration_tracking", "task": task, "artifact": artifact,
                "revision": revision, "final": group["final"], "files": [p["path"] for p in outputs]}


def predecessors(group):
    final = group["final"]
    seen, todo = set(), list(group["revisions"][final]["replaces"]) if final else []
    while todo:
        revision = todo.pop()
        if revision not in seen:
            seen.add(revision)
            todo.extend(group["revisions"][revision]["replaces"])
    return seen


def valid(entry):
    try:
        return dm.same_tree(entry["measurement"], dm.local_measure(entry["path"]))
    except (OSError, dm.Refusal):
        return False


def review(registry, task=None, artifact=None):
    protected, protected_entries = [], []
    for group in registry["groups"].values():
        superseded = predecessors(group)
        for revision, record in group["revisions"].items():
            # Every dependency stays protected, even a source from an older revision.
            protected_entries.extend(record["dependencies"])
            if revision not in superseded:
                protected_entries.extend(record["files"])
    protected = [p["path"] for p in protected_entries] + list(registry.get('notes',{}).values())
    protected_inodes = {tuple(p["measurement"]["identity"][:2]) for p in protected_entries}
    output = []
    for group in registry["groups"].values():
        if task is not None and (group["task"] != task or group["artifact"] != artifact):
            continue
        superseded = predecessors(group)
        final = group["revisions"].get(group["final"], {})
        final_valid = bool(final) and all(valid(p) for p in final["files"] + final["dependencies"])
        candidates, retained = [], []
        for revision, record in group["revisions"].items():
            for entry in record["files"]:
                reason = None
                if revision not in superseded:
                    reason = "final_or_unreplaced_branch"
                elif not final_valid:
                    reason = "final_bundle_missing_or_changed"
                elif any(dm.inside(entry["path"], p) or dm.inside(p, entry["path"]) for p in protected):
                    reason = "retained_output_or_dependency"
                elif tuple(entry["measurement"]["identity"][:2]) in protected_inodes:
                    reason = "shares_inode_with_retained_output"
                elif not valid(entry):
                    reason = "old_output_missing_or_changed"
                row = {"revision": revision, **entry}
                if reason:
                    retained.append(dict(row, reason=reason))
                else:
                    candidates.append(row)
        # Never count a reused path twice.
        unique = {p["path"]: p for p in candidates}
        output.append({"task": group["task"], "artifact": group["artifact"], "final": group["final"],
                       "final_valid": final_valid, "candidates": list(unique.values()), "retained": retained})
    return {"version": 1, "kind": "iteration_review", "groups": output,
            "protected_paths": sorted(set(protected)),
            "note": "Only explicit predecessor chains are superseded; multi-format finals and declared dependencies stay protected."}


def prune(store, task, artifact):
    with store.lock():
        registry = load(store)
        notes_path = registry.get('notes',{}).get(task)
        if notes_path and not dm.no_links(notes_path).is_file():
            raise dm.Refusal('task_notes_missing_restore_before_pruning')
        result = review(registry, task, artifact)
        candidates = [p for g in result["groups"] for p in g["candidates"]]
        # Every retained output/dependency must still match before deletion starts.
        guards = [entry for group in registry["groups"].values()
                  for rev, record in group["revisions"].items()
                  for entry in record["dependencies"] + (record["files"] if rev not in predecessors(group) else [])]
        if not all(valid(p) for p in guards):
            raise dm.Refusal("retained_bundle_changed_or_missing")
        paths = []
        for candidate in candidates:
            path = dm.no_links(candidate["path"])
            info = path.stat()
            if info.st_uid != os.getuid() or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
                raise dm.Refusal("candidate_not_owned_regular_single_link_file")
            # Runtime, chats, memory, and app-managed data must not be registered
            # as disposable output revisions, even with explicit replaces edges.
            for root in (Path.home()/'.codex', Path.home()/'.cache', Path.home()/'Library', store.root):
                if dm.inside(path, root):
                    raise dm.Refusal("protected_storage_root")
            configured = dm.lexical(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
            if (dm.inside(path, configured) or path.suffix.lower() in {'.sqlite','.sqlite3','.db','.jsonl','.bib'}
                    or any(part.lower() in {'memories','mempalace','sessions','skills','worktrees'} for part in path.parts)):
                raise dm.Refusal('protected_memory_or_working_data')
            reason = dm.process_gate(path.parent)
            if reason:
                raise dm.Refusal(reason)
            paths.append((candidate, path))
        journal = {"version": 1, "kind": "iteration_prune", "task": task, "artifact": artifact,
                   "created_at": dm.utc(), "items": [], "volumes_before": {str(p.parent): dm.volume(p) for _, p in paths}}
        name = 'result-iterations-' + uuid.uuid4().hex + '.json'
        store.write(name, journal)
        for candidate, path in paths:
            quarantine = path.parent / ('.codex-superseded-' + uuid.uuid4().hex)
            row = {"path": str(path), "quarantine": str(quarantine), "status": "starting"}
            journal["items"].append(row)
            store.write(name, journal, keep=[store.root/name])
            try:
                if not valid(candidate) or not all(valid(p) for p in guards):
                    raise dm.Refusal("bundle_changed_before_removal")
                expected = path.stat()
                path.rename(quarantine)
                moved = quarantine.stat()
                if dm.stamp(expected)[:5] != dm.stamp(moved)[:5] or moved.st_nlink != 1:
                    raise dm.Refusal("candidate_changed_during_rename")
                if dm.process_gate(quarantine.parent) or not all(valid(p) for p in guards):
                    raise dm.Refusal("bundle_in_use_or_changed")
                # File is in its own unpredictable quarantine name; no directory sweeps.
                if dm.stamp(quarantine.stat()) != dm.stamp(moved):
                    raise dm.Refusal("candidate_changed_in_quarantine")
                quarantine.unlink()
                row.update(status='removed', logical_bytes=expected.st_size,
                           allocated_bytes=candidate['measurement']['allocated_bytes'])
            except (OSError, dm.Refusal) as exc:
                if quarantine.exists() and not path.exists():
                    quarantine.rename(path)
                row.update(status='stopped_review_required', reason=type(exc).__name__)
                journal['stopped_early'] = True
                break
            finally:
                try:
                    store.write(name, journal, keep=[store.root/name])
                except (OSError, dm.Refusal):
                    journal['audit_error'] = 'record_update_failed'
            if journal.get('audit_error'):
                journal['stopped_early'] = True
                break
        journal['volumes_after'] = {str(p.parent): dm.volume(p.parent) for _, p in paths}
        journal['record_path'] = str(store.root/name)
        try:
            store.write(name,journal,keep=[store.root/name])
        except (OSError,dm.Refusal):
            journal['audit_error']='record_update_failed'
        return journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default=str(Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex'))) / 'disk-maintenance'))
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('inspect')
    p.add_argument('--root', required=True)
    p.add_argument('--seconds', type=float, default=120)
    p.add_argument('--max-entries', type=int, default=500000)
    p = sub.add_parser('track')
    p.add_argument('--task', required=True)
    p.add_argument('--artifact', required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--file', action='append', required=True)
    p.add_argument('--dependency', action='append', default=[])
    p.add_argument('--replaces', action='append', default=[])
    p.add_argument('--final', action='store_true')
    sub.add_parser('review')
    p = sub.add_parser('notes', help='Bind a single existing Markdown lessons file to a task')
    p.add_argument('--task', required=True)
    p.add_argument('--file', required=True)
    p = sub.add_parser('prune')
    p.add_argument('--task', required=True)
    p.add_argument('--artifact', required=True)
    p.add_argument('--authorize-superseded', action='store_true', required=True)
    args = parser.parse_args()
    try:
        store = dm.Store(args.state_dir)
        if args.action == 'inspect':
            if args.seconds <= 0 or args.max_entries <= 0:
                raise dm.Refusal('scan_limits_must_be_positive')
            result = inspect(args.root, args.seconds, args.max_entries)
        elif args.action == 'track':
            result = track(store,args.task,args.artifact,args.revision,args.file,args.dependency,args.replaces,args.final)
        elif args.action == 'review':
            result = review(load(store))
        elif args.action == 'notes':
            result = bind_notes(store,args.task,args.file)
        else:
            result = prune(store,args.task,args.artifact)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (dm.Refusal,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'kind':'error','reason':str(exc) if isinstance(exc,dm.Refusal) else type(exc).__name__}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
