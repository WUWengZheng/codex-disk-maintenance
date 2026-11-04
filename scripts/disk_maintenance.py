#!/usr/bin/env python3
"""Bounded, metadata-only disk accounting and conservative on-demand maintenance.

Python 3.9+, standard library. No background service, downloads, or shell commands.
"""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import heapq
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

VERSION = 1
MAX_STATE = 20 * 1024 * 1024
MAX_DOCUMENT = 8 * 1024 * 1024
TOOLS = ("uv", "pnpm", "pip", "npm")
PROTECTED = {"worktrees", "sessions", "archived_sessions", "attachments", "plugins",
             "browser", "computer-use", "generated_images", "visualizations", "skills",
             "memories", "memories_v2", "pets", "auth.json", "config.toml"}


class Refusal(Exception):
    pass


class PartialFailure(Refusal):
    pass


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def inside(path, root):
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def lexical(path):
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def no_links(path):
    """Reject links in every existing component, not just the final component."""
    path = lexical(path)
    for component in (path,) + tuple(path.parents):
        try:
            if stat.S_ISLNK(component.lstat().st_mode):
                raise Refusal("symbolic_link_in_path: " + str(component))
        except FileNotFoundError:
            continue
    return path


def read_json(path):
    path = no_links(path)
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        if os.fstat(handle.fileno()).st_size > MAX_DOCUMENT:
            raise Refusal("document_too_large")
        return json.load(handle)


def run_command(argv, timeout=10):
    """Bound output in memory and time; never return raw error/config text."""
    try:
        env = dict(os.environ, COREPACK_ENABLE_NETWORK="0", PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS="false")
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                shell=False, close_fds=True, cwd="/", env=env)
        deadline = time.monotonic() + timeout
        reason, err_seen, total, out_count = None, False, 0, 0
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, "out")
            selector.register(proc.stderr, selectors.EVENT_READ, "err")
            try:
                while selector.get_map():
                    if time.monotonic() > deadline:
                        reason = "timeout"
                        break
                    for key, _ in selector.select(timeout=min(0.05, max(0, deadline - time.monotonic()))):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(data)
                        if key.data == "out":
                            out_count += len(data)
                            output.extend(data[:max(0, 65536 - len(output))])
                        else:
                            err_seen = True
                        if total > 1024 * 1024:
                            reason = "output_limit"
                            break
                    if reason:
                        break
                if not reason:
                    try:
                        proc.wait(timeout=max(0.01, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        reason = "timeout"
                if reason and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            finally:
                proc.stdout.close()
                proc.stderr.close()
        return {"code": proc.returncode, "out": output.decode(errors="replace"),
                "err": err_seen, "reason": reason, "truncated": out_count > 65536}
    except OSError as exc:
        return {"code": None, "out": "", "err": True, "reason": type(exc).__name__}


def file_identity(path):
    info = no_links(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def stamp(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


class Store:
    def __init__(self, root):
        self.root = lexical(root)

    def ensure(self):
        no_links(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_uid != os.getuid():
            raise Refusal("state_directory_not_owned")
        if self.root.stat().st_mode & 0o077:
            raise Refusal("state_directory_must_be_private_0700")

    @contextlib.contextmanager
    def lock(self):
        self.ensure()
        fd = os.open(str(self.root / "maintenance.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refusal("maintenance_lock_busy")
            yield
        finally:
            os.close(fd)

    def key(self, create=True):
        path = self.root / "signing.key"
        if not create:
            try:
                fd = os.open(str(no_links(path)), os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as handle:
                    key = handle.read(33)
            except FileNotFoundError:
                raise Refusal("signing_key_missing")
            if len(key) != 32:
                raise Refusal("invalid_signing_key")
            return key
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            fd = os.open(str(no_links(path)), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                key = handle.read(33)
            if len(key) != 32:
                raise Refusal("invalid_signing_key")
            return key
        key = secrets.token_bytes(32)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        return key

    def sign(self, data):
        data = dict(data)
        data.pop("signature", None)
        data["signature"] = hmac.new(self.key(), canonical(data), hashlib.sha256).hexdigest()
        return data

    def verify(self, data, kind):
        if data.get("version") != VERSION or data.get("kind") != kind:
            raise Refusal("unsupported_document")
        payload = dict(data)
        payload.pop("signature", None)
        expected = hmac.new(self.key(create=False), canonical(payload), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(data.get("signature", "")), expected):
            raise Refusal("document_signature_invalid")

    def reserve(self, size, keep=None):
        self.ensure()
        keep = {str(p) for p in (keep or [])}
        files = []
        total = 0
        snapshots = []
        for p in self.root.iterdir():
            s = p.lstat()
            if not stat.S_ISREG(s.st_mode):
                raise Refusal("unexpected_state_entry")
            total += s.st_size
            if p.name.startswith(("scan-", "plan-", "result-")) and p.suffix == ".json":
                files.append((s.st_mtime_ns, str(p), s.st_size))
                if p.name.startswith("scan-"):
                    snapshots.append(str(p))
        for _, name, nbytes in sorted(files):
            excess_scans = name in snapshots and len(snapshots) >= 30
            if name not in keep and (total + size > MAX_STATE or excess_scans):
                Path(name).unlink()
                total -= nbytes
                if name in snapshots:
                    snapshots.remove(name)
        if total + size > MAX_STATE:
            raise Refusal("state_budget_exhausted")

    def write(self, name, data, keep=None):
        if Path(name).name != name:
            raise Refusal("invalid_state_filename")
        payload = canonical(data) + b"\n"
        if len(payload) > MAX_DOCUMENT:
            raise Refusal("document_too_large")
        self.reserve(len(payload), keep)
        dest = no_links(self.root / name)
        fd, temporary = tempfile.mkstemp(prefix=".write-", dir=str(self.root))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, dest)
            directory_fd = os.open(str(self.root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(dest)

    def registry(self):
        path = self.root / "registry.json"
        if not path.exists():
            return {"version": VERSION, "kind": "registry", "runs": {}}
        data = read_json(path)
        self.verify(data, "registry")
        return data

    def save_registry(self, data):
        self.write("registry.json", self.sign(data))


class Scanner:
    """Streaming tree hashes; file contents are never opened."""
    def __init__(self, seconds=120, max_entries=500000, top=30, excluded=None):
        self.deadline = time.monotonic() + seconds
        self.max_entries = max_entries
        self.count = 0
        self.seen = set()
        self.nodes = {}
        self.biggest = []
        self.top = top
        self.excluded = set(str(p) for p in (excluded or []))

    def measure(self, path, device=None):
        path = lexical(path)
        name = str(path)
        if name in self.nodes:
            return self.nodes[name]
        result = {"path": name, "complete": True, "logical_bytes": 0, "allocated_bytes": 0,
                  "files": 0, "links": 0, "hardlinks": 0, "errors": [],
                  "oldest_mtime": None, "newest_mtime": None}
        digest = hashlib.sha256()
        if time.monotonic() > self.deadline or self.count >= self.max_entries:
            result["complete"] = False
            result["errors"] = ["scan_budget_reached"]
            result["fingerprint"] = None
            self.nodes[name] = result
            return result
        self.count += 1
        try:
            s = path.lstat()
            result["identity"] = [s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode)]
            result["entry_stamp"] = stamp(s)
            # Root ctime changes on quarantine rename; child ctime is hashed by its parent.
            digest.update(canonical([s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns]))
            if device is not None and (s.st_dev != device or os.path.ismount(name)):
                raise Refusal("nested_mount_skipped")
            if name in self.excluded:
                result.update(excluded=True, fingerprint="maintenance_state_excluded")
                self.nodes[name] = result
                return result
            if stat.S_ISLNK(s.st_mode):
                result["links"] = 1
                result["link_target"] = os.readlink(name)
                digest.update(os.fsencode(result["link_target"]))
            elif stat.S_ISREG(s.st_mode):
                result["files"] = 1
                result["hardlinks"] = int(s.st_nlink > 1)
                result["oldest_mtime"] = result["newest_mtime"] = s.st_mtime
                inode = (s.st_dev, s.st_ino)
                if inode not in self.seen:
                    self.seen.add(inode)
                    result["logical_bytes"] = s.st_size
                    result["allocated_bytes"] = s.st_blocks * 512
                    item = (s.st_size, name)
                    if len(self.biggest) < self.top:
                        heapq.heappush(self.biggest, item)
                    elif item > self.biggest[0]:
                        heapq.heapreplace(self.biggest, item)
            elif stat.S_ISDIR(s.st_mode):
                children = []
                with os.scandir(name) as entries:
                    for entry in entries:
                        if time.monotonic() > self.deadline or len(children) >= self.max_entries - self.count:
                            result["complete"] = False
                            result["errors"] = ["scan_budget_reached"]
                            break
                        children.append(entry.name)
                children.sort()
                for child_name in children:
                    child_path = path / child_name
                    child = self.measure(child_path, s.st_dev)
                    try:
                        cs = child_path.lstat()
                        digest.update(canonical([child_name, cs.st_ctime_ns, child.get("fingerprint")]))
                    except OSError:
                        child = dict(child, complete=False, errors=["changed_during_scan"])
                    for key in ("logical_bytes", "allocated_bytes", "files", "links", "hardlinks"):
                        result[key] += child[key]
                    for key, fn in (("oldest_mtime", min), ("newest_mtime", max)):
                        if child[key] is not None:
                            result[key] = child[key] if result[key] is None else fn(result[key], child[key])
                    if not child["complete"]:
                        result["complete"] = False
                        result["errors"] = list(set(result["errors"] + child["errors"]))[:8]
                    if time.monotonic() > self.deadline or self.count >= self.max_entries:
                        result["complete"] = False
                        result["errors"] = list(set(result["errors"] + ["scan_budget_reached"]))
                        break
                end = path.lstat()
                if (s.st_ino, s.st_mtime_ns, s.st_ctime_ns) != (end.st_ino, end.st_mtime_ns, end.st_ctime_ns):
                    raise Refusal("directory_changed_during_scan")
            else:
                raise Refusal("special_file_skipped")
        except (OSError, Refusal, RecursionError) as exc:
            result["complete"] = False
            result["errors"] = [str(exc) if isinstance(exc, Refusal) else type(exc).__name__]
        result["fingerprint"] = digest.hexdigest() if result["complete"] else None
        self.nodes[name] = result
        return result


def native_tools(deadline=None):
    found = {}
    issues = []
    probes = {"uv": ["cache", "dir"], "pnpm": ["store", "path"],
              "pip": ["cache", "dir"], "npm": ["config", "get", "cache"]}
    for tool in TOOLS:
        if deadline is not None and time.monotonic() >= deadline:
            issues.append({"tool": tool, "reason": "discovery_budget_reached"})
            continue
        executable = shutil.which("pip3" if tool == "pip" else tool)
        if not executable:
            issues.append({"tool": tool, "reason": "not_installed"})
            continue
        executable = str(Path(executable).resolve())
        timeout = 10 if deadline is None else min(10, max(0.01, deadline - time.monotonic()))
        response = run_command([executable] + probes[tool], timeout=timeout)
        lines = response["out"].strip().splitlines()
        if response["reason"] or response["code"] != 0 or len(lines) != 1 or not os.path.isabs(lines[0]):
            issues.append({"tool": tool, "reason": "cache_location_query_failed"})
            continue
        try:
            cache = no_links(lines[0])
            if not cache.is_dir() or cache.stat().st_uid != os.getuid():
                raise Refusal("cache_not_owned_directory")
            # A misconfigured tool must never turn a home/project root into a cache target.
            if cache in (Path("/"), Path.home(), Path.home() / "Library", Path.home() / ".codex"):
                raise Refusal("unsafe_cache_root")
            timeout = 10 if deadline is None else min(10, max(0.01, deadline - time.monotonic()))
            version = run_command([executable, "--version"], timeout=timeout)
            if version["code"] != 0 or version["reason"]:
                raise Refusal("version_query_failed")
            match = re.search(r"\b(\d+)\.(\d+)", version["out"])
            minimum = {"uv": (0, 4), "pip": (20, 1), "npm": (6, 0), "pnpm": (8, 0)}[tool]
            if not match or tuple(map(int, match.groups())) < minimum:
                raise Refusal("unsupported_tool_version")
            found[tool] = {"path": str(cache), "executable": executable,
                           "executable_identity": file_identity(executable),
                           "version": version["out"].strip()[:160]}
        except (OSError, Refusal) as exc:
            issues.append({"tool": tool, "reason": str(exc) if isinstance(exc, Refusal) else type(exc).__name__})
    return found, issues


def process_gate(root, tool=None):
    """No claim of system-wide quiescence: inconclusive checks fail closed."""
    lsof = shutil.which("lsof")
    if not lsof:
        return "lsof_unavailable"
    response = run_command([lsof, "-nP", "-F", "p", "+D", str(root)], timeout=15)
    if response["reason"] or response["err"] or response.get("truncated") or response["code"] not in (0, 1):
        return "open_file_check_inconclusive"
    if re.search(r"(?m)^p\d+", response["out"]):
        return "open_files_or_working_directory"
    if tool:
        ps = shutil.which("ps")
        if not ps:
            return "process_inventory_unavailable"
        response = run_command([ps, "-axo", "pid=,comm="], timeout=10)
        if response["code"] != 0 or response["reason"] or response["err"] or response.get("truncated"):
            return "process_inventory_inconclusive"
        processes = {}
        for line in response["out"].splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2 or not parts[0].isdigit():
                return "process_inventory_inconclusive"
            if int(parts[0]) == os.getpid():
                continue
            executable = Path(parts[1]).name.lower()
            processes[int(parts[0])] = executable
            if executable in {"uv", "uvx", "pip", "pip3", "npm", "pnpm", "npx"}:
                return "package_manager_running"
            if tool in ("npm", "pnpm") and executable in ("node", "nodejs"):
                return "node_process_may_use_cache"
        response = run_command([ps, "-axo", "pid=,args="], timeout=10)
        if response["code"] != 0 or response["reason"] or response["err"] or response.get("truncated"):
            return "process_inventory_inconclusive"
        for line in response["out"].splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2 or not parts[0].isdigit():
                return "process_inventory_inconclusive"
            if tool == "pip" and processes.get(int(parts[0]), "").startswith("python"):
                if re.search(r"\s-m\s+pip(?:\s|$)|(?:^|[ /])pip[0-9.]*(?:\s|$)", parts[1]):
                    return "pip_process_running"
    return None


def volume(path):
    try:
        p = lexical(path)
        while not p.exists():
            p = p.parent
        info = os.statvfs(str(p))
        total = info.f_blocks * info.f_frsize
        free = info.f_bavail * info.f_frsize
        return {"device": p.stat().st_dev, "total_bytes": total, "available_bytes": free,
                "emergency": free < 5 * 1024**3 or (total > 0 and free / total < 0.05)}
    except OSError:
        return {"error": "volume_measurement_unavailable"}


def root_specs(codex, projects, tools, only=None):
    if only:
        return [{"path": str(no_links(p)), "category": "explicit_diagnostic", "protected": True}
                for p in only]
    roots = [{"path": str(codex), "category": "codex", "protected": True},
             {"path": str(Path.home() / ".cache" / "codex-runtimes"), "category": "runtime", "protected": True},
             {"path": str(Path.home() / "Library" / "Application Support" / "Codex"), "category": "app_data", "protected": True}]
    for name in ("Codex", "com.openai.codex"):
        roots.append({"path": str(Path.home() / "Library" / "Caches" / name),
                      "category": "app_cache_unverified", "protected": True})
    roots.append({"path": str(Path(tempfile.gettempdir()).resolve()),
                  "category": "system_temp_unattributed", "protected": True})
    roots.extend({"path": str(no_links(p)), "category": "project", "protected": True} for p in projects)
    roots.extend({"path": value["path"], "category": "shared_cache", "tool": tool,
                  "protected": False} for tool, value in tools.items())
    return roots


def scan(codex, store, projects=(), only=None, seconds=120, max_entries=500000, discover=True, candidates_only=False):
    started = time.monotonic()
    tools, issues = native_tools(deadline=started + seconds) if discover and not only else ({}, [])
    roots = root_specs(codex, projects, tools, only)
    if candidates_only:
        roots = [root for root in roots if not root["protected"]]
    registry = store.registry() if (store.root / "registry.json").exists() else {"runs": {}}
    for run in registry["runs"].values():
        if Path(run["path"]).exists() and not only:
            roots.append({"path": run["path"], "category": "registered_scratch", "protected": False})
    scanner = Scanner(max(0, seconds - (time.monotonic() - started)), max_entries, excluded=[store.root])
    safe_paths = set()
    for root in roots:
        try:
            no_links(root["path"])
            safe_paths.add(root["path"])
        except Refusal:
            scanner.nodes[root["path"]] = {"path": root["path"], "complete": False,
                "logical_bytes": 0, "allocated_bytes": 0, "files": 0,
                "errors": ["symbolic_link_in_root_components"]}
    physical_roots = []
    for path in sorted(safe_paths, key=lambda s: (len(Path(s).parts), s)):
        if not any(inside(path, parent) for parent in physical_roots):
            physical_roots.append(path)
    # Prefer known actionable roots if disk is already critically low.
    urgent = volume(codex).get("emergency", False)
    if urgent:
        physical_roots.sort(key=lambda p: not any(inside(r["path"], p) and not r["protected"] for r in roots))
        for root in sorted((r for r in roots if not r["protected"]),
                           key=lambda r: r["category"] != "registered_scratch"):
            if root["path"] in safe_paths:
                scanner.measure(root["path"])
    for root in physical_roots:
        scanner.measure(root)
    units = []
    accounting = []
    for root in roots:
        result = scanner.nodes.get(root["path"], {"path": root["path"], "complete": False,
                                                 "errors": ["not_covered_by_budget_or_mount"]})
        accounting.append(dict(root, measurement=result))
    # Disjoint top-level units provide an additive, inode-deduplicated overview.
    for root in physical_roots:
        for path, value in scanner.nodes.items():
            if str(Path(path).parent) == root or (path == root and not Path(root).is_dir()):
                units.append(value)
    units.sort(key=lambda item: item.get("allocated_bytes", 0), reverse=True)
    limited = len(units) > 1000
    return {"version": VERSION, "kind": "scan", "id": uuid.uuid4().hex, "created_at": utc(),
            "created_epoch": time.time(), "codex_home": str(codex), "projects": list(map(str, projects)),
            "coverage": accounting, "units": units[:1000], "units_truncated": limited,
            "complete": all(r["measurement"].get("complete", False) for r in accounting),
            "entries_examined": scanner.count, "elapsed_seconds": round(time.monotonic() - started, 3),
            "tools": tools, "discovery_issues": issues,
            "largest_files": [{"path": p, "logical_bytes": n} for n, p in sorted(scanner.biggest, reverse=True)],
            "volumes": {p: volume(p) for p in physical_roots},
            "accounting_note": "Hardlinks counted once across this scan; allocated blocks may share APFS extents. Root summaries overlap and must not be summed.",
            "attribution_note": "Shared caches and system temp are not proven to have been created by Codex."}


def diff_scans(before, after):
    def mapping(doc):
        return {item["path"]: item["measurement"] for item in doc["coverage"]}
    old, new = mapping(before), mapping(after)
    changes, excluded = [], []
    for path in sorted(set(old) | set(new)):
        a, b = old.get(path), new.get(path)
        if not a or not b or not a.get("complete") or not b.get("complete"):
            excluded.append({"path": path, "reason": "coverage_changed_or_incomplete"})
            continue
        # Inode attribution changes when root sets change; compare logical coverage separately.
        same_scope = sorted(old) == sorted(new)
        if not same_scope:
            excluded.append({"path": path, "reason": "root_set_changed_inode_attribution_not_comparable"})
            continue
        changes.append({"path": path, "logical_delta_bytes": b["logical_bytes"] - a["logical_bytes"],
                        "allocated_delta_bytes": b["allocated_bytes"] - a["allocated_bytes"] if same_scope else None,
                        "allocation_comparable": same_scope})
    return {"version": VERSION, "kind": "diff", "before": before["id"], "after": after["id"],
            "changes": changes, "excluded": excluded,
            "note": "Root rows may overlap; do not sum. Changes establish correlation, not task causation."}


def scratch_parent(codex):
    return no_links(codex / "tmp" / "disk-maintenance")


def scratch_action(codex, store, action, run_id=None, keep=()):
    with store.lock():
        registry = store.registry()
        if action == "create":
            run_id = uuid.uuid4().hex
            parent = scratch_parent(codex)
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = parent / run_id
            path.mkdir(mode=0o700)
            record = {"path": str(path), "id": run_id, "created_at": utc(),
                      "identity": Scanner().measure(path)["identity"], "status": "active",
                      "disposable": True, "keep": []}
            registry["runs"][run_id] = record
            try:
                store.save_registry(registry)
            except Exception:
                path.rmdir()  # Only the newly created, still-empty directory.
                raise
        else:
            if run_id not in registry["runs"]:
                raise Refusal("unknown_scratch_run")
            record = registry["runs"][run_id]
            expected = scratch_parent(codex) / run_id
            if record["path"] != str(expected) or record["status"] not in ("active", "finished"):
                raise Refusal("invalid_scratch_state")
            for item in keep:
                p = Path(item)
                if p.is_absolute() or ".." in p.parts:
                    raise Refusal("keep_path_must_be_relative")
            record["keep"] = sorted(set(record["keep"]) | set(keep))
            record["status"] = "finished"
            # Repeated finish never shortens the cooling period.
            record["finished_epoch"] = time.time()
            store.save_registry(registry)
        return {"version": VERSION, "kind": "scratch", "run": record}


def eligible_scratch(record, codex, now=None):
    now = time.time() if now is None else now
    run_id = record.get("id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        return "invalid_run_id"
    if record.get("path") != str(scratch_parent(codex) / run_id):
        return "scratch_path_mismatch"
    if record.get("status") != "finished" or record.get("disposable") is not True:
        return "task_not_finished"
    if now - record.get("finished_epoch", now) < 24 * 3600:
        return "cooling_period_24h"
    if record.get("keep"):
        return "declared_artifacts_preserved"
    return None


def clean_argv(tool, info):
    exe, root = info["executable"], info["path"]
    if tool == "uv":
        return [exe, "cache", "prune", "--cache-dir", root]
    if tool == "pnpm":
        return [exe, "--store-dir", root, "store", "prune"]
    if tool == "pip":
        return [exe, "--cache-dir", root, "cache", "purge"]
    if tool == "npm":
        return [exe, "--cache", root, "cache", "clean", "--force"]
    raise Refusal("unsupported_tool")


def uv_gate():
    # Historical symlink installations cannot be proved safe by checking current
    # defaults. Require explicit operator knowledge before even proposing uv prune.
    return None if os.environ.get("DISK_MAINTENANCE_UV_NO_SYMLINK_DEPENDENCIES") == "1" else "uv_symlink_dependency_safety_unverified"


def cache_path_gate(path, codex, projects=(), tool=None):
    path = no_links(path)
    # Never treat a project, skill, app runtime or Codex subtree as a cache merely
    # because an environment variable or a CLI setting points there.
    forbidden = [codex, Path.home() / ".cache" / "codex-runtimes",
                 Path.home() / "Library" / "Application Support"] + [lexical(p) for p in projects]
    for root in forbidden:
        if inside(path, root) or inside(root, path):
            return "cache_overlaps_protected_root"
    if path == Path.home() or len(path.parts) < 4:
        return "unsafe_cache_root"
    home = Path.home()
    xdg = lexical(os.environ.get("XDG_CACHE_HOME", str(home / ".cache")))
    standard = {
        "pip": [home / "Library/Caches/pip", xdg / "pip"],
        "uv": [xdg / "uv", home / "Library/Caches/uv"],
        "npm": [home / ".npm", xdg / "npm", home / "Library/Caches/npm"],
        "pnpm": [home / "Library/pnpm/store", home / ".local/share/pnpm/store",
                 home / "Library/Caches/pnpm", xdg / "pnpm/store"],
    }
    if tool not in standard or not any(path == root or (tool == "pnpm" and inside(path, root)) for root in standard[tool]):
        return "custom_cache_location_requires_future_adapter"
    return None


def make_plan(scan_doc, codex, store, full_cache_clear=False):
    store.verify(scan_doc, "scan")
    if scan_doc["codex_home"] != str(codex):
        raise Refusal("codex_home_mismatch")
    if time.time() - scan_doc["created_epoch"] > 900:
        raise Refusal("scan_expired_rescan_required")
    registry = store.registry()
    coverage = {r["path"]: r for r in scan_doc["coverage"]}
    items, rejected = [], []
    for run_id, record in registry["runs"].items():
        reason = eligible_scratch(record, codex)
        row = coverage.get(record["path"])
        measurement = row["measurement"] if row else {}
        if not measurement.get("complete"):
            reason = reason or "scratch_scan_incomplete"
        if measurement.get("links") or measurement.get("hardlinks"):
            reason = reason or "scratch_links_need_manual_review"
        if measurement.get("identity") != record.get("identity"):
            reason = reason or "scratch_identity_changed"
        if reason:
            rejected.append({"path": record["path"], "reason": reason})
            continue
        items.append({"id": "scratch-" + run_id, "scope": "scratch", "run_id": run_id,
                      "path": record["path"], "measurement": measurement,
                      "evidence": "signed_registry_finished_24h_no_declared_artifacts",
                      "action": "remove_registered_scratch", "status": "candidate",
                      "impact": "Discardable intermediate files are permanently removed; no backup is made."})
    for tool, info in scan_doc["tools"].items():
        if tool not in TOOLS:
            continue
        reason = cache_path_gate(info["path"], codex, scan_doc["projects"], tool)
        row = coverage.get(info["path"])
        measurement = row["measurement"] if row else {}
        if not measurement.get("complete"):
            reason = reason or "cache_scan_incomplete"
        if tool in ("pip", "npm") and not full_cache_clear:
            reason = reason or "full_cache_clear_not_requested"
        if tool == "uv":
            reason = reason or uv_gate()
        if reason:
            rejected.append({"path": info["path"], "tool": tool, "reason": reason})
            continue
        items.append({"id": "cache-" + tool, "scope": tool, "path": info["path"],
                      "tool": info, "measurement": measurement, "action": "native_cache_maintenance",
                      "evidence": "native_tool_reported_cache_path; shared across projects",
                      "status": "candidate", "full_cache_clear": tool in ("pip", "npm"),
                      "impact": "Future installs may download/build again; cache size is an upper bound, not promised reclaimed space.",
                      "preview": "Scope only; native command has no exact deletion dry-run."})
    return store.sign({"version": VERSION, "kind": "plan", "id": uuid.uuid4().hex,
                       "created_at": utc(), "created_epoch": time.time(), "expires_epoch": time.time() + 900,
                       "scan_id": scan_doc["id"], "codex_home": str(codex),
                       "projects": scan_doc["projects"], "items": items, "rejected": rejected})


def local_measure(path):
    no_links(path)
    return Scanner(seconds=120, max_entries=500000).measure(path)


def same_tree(a, b):
    return (a.get("complete") and b.get("complete") and a.get("identity") == b.get("identity")
            and a.get("fingerprint") == b.get("fingerprint"))


def remove_verified_tree(path, nodes):
    """Only unlink measured inodes; never recursively sweep newly arrived files.

    Renaming each file to an unpredictable name before final identity validation
    avoids unlinking a replacement at its old name. New arrivals make rmdir fail
    and remain in the recorded quarantine for review.
    """
    for function in (os.open, os.stat, os.rename, os.unlink, os.rmdir):
        if function not in os.supports_dir_fd:
            raise Refusal("directory_fd_operations_unavailable")
    children = {}
    for name in nodes:
        children.setdefault(str(Path(name).parent), []).append(Path(name).name)

    def remove_dir(parent_fd, basename, full_path):
        expected = nodes[full_path]["entry_stamp"]
        fd = os.open(basename, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            if stamp(os.fstat(fd)) != expected:
                raise Refusal("directory_changed_during_removal")
            names = sorted(os.listdir(fd))
            if names != sorted(children.get(full_path, [])):
                raise Refusal("new_entries_during_removal")
            for name in names:
                child_path = str(Path(full_path) / name)
                expected_child = nodes[child_path]["entry_stamp"]
                current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stamp(current) != expected_child:
                    raise Refusal("entry_changed_during_removal")
                if stat.S_ISDIR(current.st_mode):
                    remove_dir(fd, name, child_path)
                elif stat.S_ISREG(current.st_mode) and current.st_nlink == 1:
                    temporary_name = ".unlink-" + uuid.uuid4().hex
                    os.rename(name, temporary_name, src_dir_fd=fd, dst_dir_fd=fd)
                    moved = os.stat(temporary_name, dir_fd=fd, follow_symlinks=False)
                    if stamp(moved)[:5] != expected_child[:5] or moved.st_nlink != 1:
                        # Keep the moved object; never overwrite a new source name.
                        raise Refusal("file_changed_during_unlink_rename")
                    os.unlink(temporary_name, dir_fd=fd)
                else:
                    raise Refusal("unsupported_entry_during_removal")
            current = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
            if [current.st_dev, current.st_ino] != expected[:2]:
                raise Refusal("directory_replaced_during_removal")
            os.rmdir(basename, dir_fd=parent_fd)
        finally:
            os.close(fd)

    parent_fd = os.open(str(no_links(path.parent)), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        remove_dir(parent_fd, path.name, str(path))
    finally:
        os.close(parent_fd)


def remove_scratch(item, codex, store, registry):
    run_id = item["run_id"]
    record = registry["runs"].get(run_id, {})
    reason = eligible_scratch(record, codex)
    if reason or record.get("path") != item["path"]:
        raise Refusal(reason or "registry_path_changed")
    path = no_links(record["path"])
    if path.stat().st_uid != os.getuid():
        raise Refusal("scratch_owner_changed")
    before = local_measure(path)
    if before.get("links") or before.get("hardlinks") or not same_tree(before, item["measurement"]):
        raise Refusal("scratch_changed_or_incomplete")
    if before["identity"] != record.get("identity"):
        raise Refusal("scratch_identity_changed")
    reason = process_gate(path)
    if reason:
        raise Refusal(reason)
    # Check again after the potentially slow open-file inspection.
    if not same_tree(before, local_measure(path)):
        raise Refusal("scratch_changed_before_quarantine")
    quarantine = scratch_parent(codex) / (".pending-" + uuid.uuid4().hex)
    record.update(status="quarantining", quarantine=str(quarantine))
    store.save_registry(registry)  # Must be durable before any rename or deletion.
    path.rename(quarantine)
    reason = process_gate(quarantine)
    final_scanner = Scanner()
    renamed = final_scanner.measure(quarantine)
    if not same_tree(before, renamed) or reason:
        # Never replace a path that another task recreated.
        if not path.exists():
            quarantine.rename(path)
            record.update(status="finished")
            record.pop("quarantine", None)
        else:
            record.update(status="quarantined_review_required")
        store.save_registry(registry)
        raise Refusal(reason or "quarantine_revalidation_failed")
    record["status"] = "deleting"
    store.save_registry(registry)
    try:
        remove_verified_tree(quarantine, final_scanner.nodes)
    except (OSError, Refusal) as exc:
        record["status"] = "quarantined_review_required"
        store.save_registry(registry)
        raise PartialFailure("removal_interrupted_quarantine_retained: " + type(exc).__name__)
    # Keep history in the result journal; registry only needs live/recoverable runs.
    del registry["runs"][run_id]
    store.save_registry(registry)
    return {"status": "completed", "action": "remove_registered_scratch"}


def native_cleanup(item, codex, projects):
    tool = item["scope"]
    if tool not in TOOLS or item.get("action") != "native_cache_maintenance":
        raise Refusal("unsupported_action")
    current, issues = native_tools()
    if current.get(tool) != item["tool"] or item["path"] != current.get(tool, {}).get("path"):
        raise Refusal("tool_cache_binding_changed")
    reason = cache_path_gate(item["path"], codex, projects, tool)
    if tool == "uv":
        reason = reason or uv_gate()
    if reason:
        raise Refusal(reason)
    before = local_measure(item["path"])
    if not same_tree(before, item["measurement"]):
        raise Refusal("cache_changed_or_incomplete")
    reason = process_gate(item["path"], tool)
    if reason:
        raise Refusal(reason)
    if not same_tree(before, local_measure(item["path"])):
        raise Refusal("cache_changed_before_execution")
    response = run_command(clean_argv(tool, current[tool]), timeout=60)
    if response["reason"]:
        return {"status": "possibly_partial", "reason": response["reason"], "stop_remaining": True}
    if response["code"] != 0:
        return {"status": "failed_possibly_partial", "reason": "native_command_failed_or_unsupported",
                "exit_code": response["code"], "stop_remaining": True}
    return {"status": "completed", "action": "native_cache_maintenance", "exit_code": 0}


def space_diagnostics(path):
    result = {"note": "Possible explanations only. No processes stopped or snapshots removed."}
    lsof = shutil.which("lsof")
    if lsof:
        response = run_command([lsof, "-nP", "+L1", "-F", "p"], timeout=10)
        result["open_deleted_file_check"] = ("inconclusive" if response["reason"] or response["err"]
                                             else "possible_holders_present" if response["out"].strip() else "none_observed")
    if sys.platform == "darwin" and shutil.which("tmutil"):
        response = run_command([shutil.which("tmutil"), "listlocalsnapshots", str(path)], timeout=10)
        result["snapshot_check"] = ("inconclusive" if response["code"] != 0 or response["reason"]
                                    else "snapshots_observed" if re.search(r"com\.apple\.", response["out"]) else "none_observed")
    return result


def apply_plan(doc, codex, store, authorize, ids=None):
    with store.lock():
        store.verify(doc, "plan")
        if doc["codex_home"] != str(codex) or time.time() > doc["expires_epoch"]:
            raise Refusal("plan_expired_or_wrong_codex_home")
        if ids and set(ids) - {i["id"] for i in doc["items"]}:
            raise Refusal("unknown_item_id")
        result_id = "result-" + uuid.uuid4().hex + ".json"
        result = {"version": VERSION, "kind": "result", "plan_id": doc["id"],
                  "created_at": utc(), "items": [], "note": "Volume deltas are observations, not exclusive attribution to this cleanup."}
        registry = store.registry()
        # Preflight enough audit headroom. A failed write aborts before mutation.
        store.reserve(256 * 1024)
        store.write(result_id, result)
        for item in doc["items"]:
            if (ids and item["id"] not in ids) or item["scope"] not in authorize:
                result["items"].append({"id": item["id"], "status": "skipped", "reason": "outside_authorized_selection"})
                continue
            row = {"id": item["id"], "path": item["path"], "status": "starting"}
            result["items"].append(row)
            before_volume = volume(item["path"])
            row["volume_before"] = before_volume
            try:
                store.write(result_id, result, keep=[store.root / result_id])
            except (OSError, Refusal) as exc:
                row.update(status="skipped", reason="audit_record_unwritable")
                result.update(stopped_early=True, audit_error=type(exc).__name__)
                break
            try:
                before = local_measure(item["path"])
                row["measurement_before"] = before
                if item["scope"] == "scratch" and item.get("action") == "remove_registered_scratch":
                    row.update(remove_scratch(item, codex, store, registry))
                elif item["scope"] in TOOLS:
                    row.update(native_cleanup(item, codex, doc["projects"]))
                else:
                    raise Refusal("unsupported_action")
            except PartialFailure as exc:
                row.update(status="failed_possibly_partial", reason=str(exc), stop_remaining=True)
            except Refusal as exc:
                row.update(status="skipped", reason=str(exc))
            except OSError as exc:
                row.update(status="failed_possibly_partial", reason=type(exc).__name__, stop_remaining=True)
            try:
                retained = [item["path"]] if os.path.lexists(item["path"]) else []
                if item["scope"] == "scratch":
                    quarantine = registry["runs"].get(item["run_id"], {}).get("quarantine")
                    if quarantine and os.path.lexists(quarantine):
                        retained.append(quarantine)
                        row["retained_quarantine_path"] = quarantine
                after_scanner = Scanner()
                parts = [after_scanner.measure(no_links(p)) for p in retained]
                after = {"complete": all(p["complete"] for p in parts),
                         "logical_bytes": sum(p["logical_bytes"] for p in parts),
                         "allocated_bytes": sum(p["allocated_bytes"] for p in parts),
                         "files": sum(p["files"] for p in parts), "retained_locations": retained}
            except (OSError, Refusal):
                after = {"complete": False}
            row["measurement_after"] = after
            row["volume_after"] = volume(item["path"])
            if row.get("measurement_before", {}).get("complete") and after.get("complete"):
                row["allocated_reduction_bytes"] = row["measurement_before"]["allocated_bytes"] - after["allocated_bytes"]
                row["logical_reduction_bytes"] = row["measurement_before"]["logical_bytes"] - after["logical_bytes"]
            if "available_bytes" in before_volume and "available_bytes" in row["volume_after"]:
                row["observed_volume_free_delta_bytes"] = row["volume_after"]["available_bytes"] - before_volume["available_bytes"]
                if row["status"] == "completed" and row["observed_volume_free_delta_bytes"] <= 0:
                    row["diagnostics"] = space_diagnostics(item["path"])
            try:
                store.write(result_id, result, keep=[store.root / result_id])
            except (OSError, Refusal) as exc:
                result.update(stopped_early=True, audit_error=type(exc).__name__)
                break
            if row.get("stop_remaining"):
                result["stopped_early"] = True
                break
        result["record_path"] = str(store.root / result_id)
        try:
            store.write(result_id, result, keep=[store.root / result_id])
        except (OSError, Refusal) as exc:
            result["audit_error"] = type(exc).__name__
        return result


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--state-dir", help="Private metadata directory; defaults to CODEX_HOME/disk-maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="Read-only metadata scan unless --save-baseline is supplied")
    p.add_argument("--project", action="append", default=[])
    p.add_argument("--root", action="append", help="Diagnostic-only roots; disables default roots and cache discovery")
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--max-entries", type=int, default=500000)
    p.add_argument("--save-baseline", action="store_true")
    p.add_argument("--candidates-only", action="store_true", help="Focus on registered scratch and native caches without increasing scan budgets")
    p = sub.add_parser("diff")
    p.add_argument("before", nargs="?", help="Omit both paths to compare latest two saved scans")
    p.add_argument("after", nargs="?")
    p = sub.add_parser("plan")
    p.add_argument("--scan", required=True, help="Signed saved baseline path")
    p.add_argument("--include-full-cache-clear", action="store_true", help="Include pip/npm whole-cache actions")
    p = sub.add_parser("apply")
    p.add_argument("--plan", required=True)
    p.add_argument("--authorize", nargs="+", choices=["scratch"] + list(TOOLS), required=True)
    p.add_argument("--ids", nargs="+")
    p = sub.add_parser("scratch")
    s = p.add_subparsers(dest="scratch_action", required=True)
    s.add_parser("create")
    p = s.add_parser("finish")
    p.add_argument("--run-id", required=True)
    p.add_argument("--keep", action="append", default=[])
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        codex = no_links(args.codex_home)
        store = Store(args.state_dir or codex / "disk-maintenance")
        if args.command == "scan":
            if args.seconds <= 0 or args.max_entries <= 0:
                raise Refusal("scan_limits_must_be_positive")
            if args.root and args.candidates_only:
                raise Refusal("root_and_candidates_only_are_mutually_exclusive")
            result = scan(codex, store, args.project, args.root, args.seconds, args.max_entries,
                          candidates_only=args.candidates_only)
            if args.save_baseline:
                with store.lock():
                    result = store.sign(result)
                    result["saved_path"] = str(store.root / ("scan-" + result["id"] + ".json"))
                    result = store.sign(result)
                    store.write(Path(result["saved_path"]).name, result)
        elif args.command == "scratch":
            result = scratch_action(codex, store, args.scratch_action, getattr(args, "run_id", None), getattr(args, "keep", []))
        elif args.command == "diff":
            if bool(args.before) != bool(args.after):
                raise Refusal("provide_both_scan_paths_or_neither")
            if args.before:
                paths = [Path(args.before), Path(args.after)]
            else:
                paths = sorted(store.root.glob("scan-*.json"), key=lambda p: p.stat().st_mtime_ns)[-2:]
                if len(paths) < 2:
                    raise Refusal("two_baselines_required")
            docs = [read_json(p) for p in paths]
            for doc in docs:
                if doc.get("version") != VERSION or doc.get("kind") != "scan":
                    raise Refusal("unsupported_document")
            result = diff_scans(*docs)
        elif args.command == "plan":
            with store.lock():
                result = make_plan(read_json(args.scan), codex, store, args.include_full_cache_clear)
                result["saved_path"] = str(store.root / ("plan-" + result["id"] + ".json"))
                result = store.sign(result)
                store.write(Path(result["saved_path"]).name, result, keep=[Path(args.scan)])
        else:
            result = apply_plan(read_json(args.plan), codex, store, args.authorize, args.ids)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"version": VERSION, "kind": "error", "reason": str(exc) if isinstance(exc, Refusal) else type(exc).__name__}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
