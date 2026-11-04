import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("maintenance", Path(__file__).parents[1] / "scripts/disk_maintenance.py")
dm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dm)


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="disk-maintenance-test-")
        self.base = Path(self.temp.name).resolve()
        self.codex = self.base / "codex"
        self.codex.mkdir()
        self.store = dm.Store(self.base / "state")
        original_roots = dm.root_specs
        def isolated_roots(*args, **kwargs):
            return [row for row in original_roots(*args, **kwargs) if dm.inside(row["path"], self.base)]
        self.roots_patch = mock.patch.object(dm, "root_specs", side_effect=isolated_roots)
        self.roots_patch.start()

    def tearDown(self):
        self.roots_patch.stop()
        self.temp.cleanup()

    def aged_scratch(self, keep=()):
        record = dm.scratch_action(self.codex, self.store, "create")["run"]
        path = Path(record["path"])
        (path / "intermediate.txt").write_text("discard me")
        dm.scratch_action(self.codex, self.store, "finish", record["id"], keep)
        with self.store.lock():
            registry = self.store.registry()
            registry["runs"][record["id"]]["finished_epoch"] -= 90000
            self.store.save_registry(registry)
        return record, path

    def scratch_plan(self):
        doc = dm.scan(self.codex, self.store, discover=False)
        with self.store.lock():
            return dm.make_plan(self.store.sign(doc), self.codex, self.store)

    def test_metadata_only_symlinks_hardlinks_and_sparse(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret").write_text("protected")
        root = self.base / "scan"
        root.mkdir()
        (root / "link").symlink_to(outside, target_is_directory=True)
        (root / "file").write_bytes(b"x" * 8192)
        os.link(root / "file", root / "hardlink")
        with (root / "sparse").open("wb") as f:
            f.truncate(2 * 1024 * 1024)
        scanner = dm.Scanner()
        with mock.patch("builtins.open", side_effect=AssertionError("contents must not be read")):
            result = scanner.measure(root)
        self.assertTrue(result["complete"])
        self.assertEqual(result["logical_bytes"], 8192 + 2 * 1024 * 1024)
        self.assertEqual(result["links"], 1)
        self.assertNotIn(str(outside / "secret"), scanner.nodes)
        self.assertLess(result["allocated_bytes"], result["logical_bytes"])

    def test_overlapping_roots_and_coverage_change(self):
        p = self.codex / "nested"
        p.mkdir()
        (p / "file").write_bytes(b"abc")
        one = dm.scan(self.codex, self.store, only=[self.codex], discover=False)
        two = dm.scan(self.codex, self.store, only=[self.codex, p], discover=False)
        self.assertEqual(two["coverage"][0]["measurement"]["logical_bytes"], 3)
        self.assertEqual(two["entries_examined"], 3)
        diff = dm.diff_scans(one, two)
        self.assertEqual(diff["changes"], [])
        self.assertTrue(diff["excluded"])

    def test_budget_incomplete_and_diff_excludes_it(self):
        (self.codex / "file").write_text("x")
        full = dm.scan(self.codex, self.store, only=[self.codex])
        partial = dm.scan(self.codex, self.store, only=[self.codex], max_entries=1)
        self.assertFalse(partial["complete"])
        self.assertEqual(dm.diff_scans(full, partial)["changes"], [])

    def test_growth_delta_and_largest_files(self):
        p = self.codex / "data"
        p.write_bytes(b"a")
        a = dm.scan(self.codex, self.store, only=[self.codex])
        p.write_bytes(b"a" * 101)
        b = dm.scan(self.codex, self.store, only=[self.codex])
        self.assertEqual(dm.diff_scans(a, b)["changes"][0]["logical_delta_bytes"], 100)
        self.assertEqual(b["largest_files"][0]["path"], str(p))

    def test_permissions_mount_and_deadline_fail_closed(self):
        (self.codex / "child").mkdir()
        with mock.patch.object(dm.os.path, "ismount", return_value=True):
            self.assertFalse(dm.Scanner().measure(self.codex)["complete"])
        self.assertFalse(dm.Scanner(seconds=-1).measure(self.codex)["complete"])
        with mock.patch.object(dm.os, "scandir", side_effect=PermissionError):
            self.assertFalse(dm.Scanner().measure(self.codex)["complete"])

    def test_real_scratch_deletion_and_protected_content_survives(self):
        record, path = self.aged_scratch()
        protected = self.codex / "worktrees"
        protected.mkdir()
        (protected / "untracked.md").write_text("important")
        plan = self.scratch_plan()
        self.assertEqual(len(plan["items"]), 1)
        with mock.patch.object(dm, "process_gate", return_value=None):
            result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertFalse(path.exists())
        self.assertEqual((protected / "untracked.md").read_text(), "important")
        self.assertEqual(result["items"][0]["status"], "completed")
        self.assertGreater(result["items"][0]["logical_reduction_bytes"], 0)
        self.assertEqual(self.store.registry()["runs"], {})

    def test_unregistered_directories_never_become_candidates(self):
        p = self.codex / "tmp" / "old-cache"
        p.mkdir(parents=True)
        (p / "old").write_text("unknown")
        self.assertEqual(self.scratch_plan()["items"], [])

    def test_active_recent_and_declared_artifacts_preserved(self):
        active = dm.scratch_action(self.codex, self.store, "create")["run"]
        recent = dm.scratch_action(self.codex, self.store, "create")["run"]
        dm.scratch_action(self.codex, self.store, "finish", recent["id"])
        kept, path = self.aged_scratch(keep=["intermediate.txt"])
        plan = self.scratch_plan()
        self.assertFalse(plan["items"])
        self.assertEqual(len(plan["rejected"]), 3)
        self.assertTrue(path.exists())

    def test_scratch_symbolic_and_hard_links_preserved(self):
        _, path = self.aged_scratch()
        (path / "link").symlink_to(self.codex / "auth.json")
        self.assertFalse(self.scratch_plan()["items"])
        (path / "link").unlink()
        os.link(path / "intermediate.txt", self.base / "another-link")
        self.assertFalse(self.scratch_plan()["items"])

    def test_tampered_scan_and_plan_are_rejected(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        plan["items"][0]["path"] = str(self.codex)
        with self.assertRaises(dm.Refusal):
            dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        scan = self.store.sign(dm.scan(self.codex, self.store, discover=False))
        scan["complete"] = "tampered"
        with self.assertRaises(dm.Refusal):
            dm.make_plan(scan, self.codex, self.store)
        self.assertTrue(path.exists())

    def test_changed_files_expiry_and_scope_are_rejected(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        skipped = dm.apply_plan(plan, self.codex, self.store, ["pip"])
        self.assertEqual(skipped["items"][0]["reason"], "outside_authorized_selection")
        (path / "new-result.docx").write_text("keep")
        result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertEqual(result["items"][0]["status"], "skipped")
        self.assertTrue(path.exists())
        plan["expires_epoch"] = 0
        plan = self.store.sign(plan)
        with self.assertRaises(dm.Refusal):
            dm.apply_plan(plan, self.codex, self.store, ["scratch"])

    def test_open_file_and_post_rename_race_do_not_delete(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        with mock.patch.object(dm, "process_gate", return_value="open_files_or_working_directory"):
            result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertTrue(path.exists())
        self.assertEqual(result["items"][0]["status"], "skipped")
        calls = []
        def race(root, tool=None):
            calls.append(root)
            if Path(root).name.startswith(".pending-"):
                (Path(root) / "late-result").write_text("must survive")
                return "open_files_or_working_directory"
            return None
        with mock.patch.object(dm, "process_gate", side_effect=race):
            result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertTrue((path / "late-result").exists())
        self.assertEqual(result["items"][0]["status"], "skipped")

    def test_lock_conflict_and_disk_full_before_mutation(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        with self.store.lock():
            with self.assertRaises(dm.Refusal):
                dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        with mock.patch.object(self.store, "write", side_effect=OSError(28, "No space")):
            with self.assertRaises(OSError):
                dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertTrue(path.exists())

    def test_registry_failure_after_rename_retains_recoverable_files(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        original = self.store.save_registry
        def fail_deleting(registry):
            if next(iter(registry["runs"].values()))["status"] == "deleting":
                raise OSError(28, "No space")
            return original(registry)
        with mock.patch.object(self.store, "save_registry", side_effect=fail_deleting), mock.patch.object(dm, "process_gate", return_value=None):
            result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertEqual(result["items"][0]["status"], "failed_possibly_partial")
        registry = self.store.registry()
        run = next(iter(registry["runs"].values()))
        self.assertTrue((Path(run["quarantine"]) / "intermediate.txt").exists())
        self.assertEqual(result["items"][0]["logical_reduction_bytes"], 0)
        self.assertEqual(result["items"][0]["retained_quarantine_path"], run["quarantine"])

    @contextlib.contextmanager
    def fake_tool(self, tool="pip", fail=False):
        home = self.base / "home"
        cache = home / "Library/Caches" / tool
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "package.whl").write_bytes(b"package-data")
        executable = self.base / (tool + "-fixture")
        events = self.base / "events.jsonl"
        source = '''#!{python}
import sys, json
from pathlib import Path
args = sys.argv[1:]
cache = Path({cache!r})
if args == ["--version"]:
    print("pip 26.0" if {tool!r} == "pip" else "12.0.0")
elif args in (["cache", "dir"], ["store", "path"], ["config", "get", "cache"]):
    print(cache)
else:
    with open({events!r}, "a") as f: f.write(json.dumps(args) + "\\n")
    (cache / "package.whl").unlink(missing_ok=True)
    sys.exit({exitcode})
'''.format(python=sys.executable, cache=str(cache), tool=tool, events=str(events), exitcode=7 if fail else 0)
        executable.write_text(source)
        executable.chmod(0o700)
        def which(name):
            return str(executable) if name == ("pip3" if tool == "pip" else tool) else None
        with mock.patch.object(dm.shutil, "which", side_effect=which), mock.patch.object(dm.Path, "home", return_value=home):
            yield cache, executable, events

    def cache_plan(self, full=True):
        doc = dm.scan(self.codex, self.store)
        with self.store.lock():
            return dm.make_plan(self.store.sign(doc), self.codex, self.store, full)

    def test_native_tool_binding_fixed_arguments_and_actual_fixture_cleanup(self):
        with self.fake_tool() as (cache, exe, events):
            plan = self.cache_plan()
            self.assertEqual(len(plan["items"]), 1)
            with mock.patch.object(dm, "process_gate", return_value=None):
                result = dm.apply_plan(plan, self.codex, self.store, ["pip"])
            self.assertEqual(result["items"][0]["status"], "completed")
            self.assertFalse((cache / "package.whl").exists())
            self.assertEqual(json.loads(events.read_text().splitlines()[0]), ["--cache-dir", str(cache), "cache", "purge"])

    def test_full_clear_requires_explicit_planning_and_cache_change_skips(self):
        with self.fake_tool() as (cache, exe, events):
            self.assertFalse(self.cache_plan(full=False)["items"])
            plan = self.cache_plan()
            (cache / "new-file").write_text("changed")
            with mock.patch.object(dm, "process_gate", return_value=None):
                result = dm.apply_plan(plan, self.codex, self.store, ["pip"])
            self.assertEqual(result["items"][0]["reason"], "cache_changed_or_incomplete")
            self.assertFalse(events.exists())

    def test_partial_native_failure_stops_remaining(self):
        with self.fake_tool(fail=True):
            plan = self.cache_plan()
            with mock.patch.object(dm, "process_gate", return_value=None):
                result = dm.apply_plan(plan, self.codex, self.store, ["pip"])
            self.assertEqual(result["items"][0]["status"], "failed_possibly_partial")
            self.assertTrue(result["stopped_early"])

    def test_all_native_command_arguments_are_bound(self):
        info = {"executable": "/fixture/tool", "path": "/fixture/cache with spaces"}
        expected = {
            "uv": ["cache", "prune", "--cache-dir", info["path"]],
            "pnpm": ["--store-dir", info["path"], "store", "prune"],
            "pip": ["--cache-dir", info["path"], "cache", "purge"],
            "npm": ["--cache", info["path"], "cache", "clean", "--force"],
        }
        for tool, tail in expected.items():
            self.assertEqual(dm.clean_argv(tool, info), [info["executable"]] + tail)
        with self.assertRaises(dm.Refusal):
            dm.clean_argv("arbitrary-shell", info)

    def test_cache_protection_and_uv_unknown_state(self):
        self.assertIsNotNone(dm.cache_path_gate(self.codex / "plugins/cache", self.codex, tool="pip"))
        self.assertIsNotNone(dm.cache_path_gate(self.base / "project", self.codex, tool="pip"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNotNone(dm.uv_gate())

    def test_tool_missing_and_unsupported_version_do_not_install(self):
        with mock.patch.object(dm.shutil, "which", return_value=None), mock.patch.object(dm, "run_command") as runner:
            tools, issues = dm.native_tools()
            self.assertFalse(tools)
            self.assertEqual(len(issues), 4)
            runner.assert_not_called()
        with self.fake_tool() as (cache, exe, events):
            original = dm.run_command
            def old_version(argv, timeout=10):
                if argv[1:] == ["--version"]:
                    return {"code": 0, "out": "pip 1.0", "reason": None, "err": False}
                return original(argv, timeout)
            with mock.patch.object(dm, "run_command", side_effect=old_version):
                self.assertFalse(dm.native_tools()[0])
            self.assertFalse(events.exists())

    def test_command_timeout_and_output_limit_without_disk_spooling(self):
        result = dm.run_command([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1)
        self.assertEqual(result["reason"], "timeout")
        result = dm.run_command([sys.executable, "-c", "import sys; sys.stdout.write('x'*3000000)"], timeout=3)
        self.assertEqual(result["reason"], "output_limit")
        self.assertLessEqual(len(result["out"]), 65536)

    def test_process_inventory_and_lsof_fail_closed(self):
        with mock.patch.object(dm.shutil, "which", return_value="/fixture/lsof"), mock.patch.object(dm, "run_command", return_value={"code": 1, "out": "", "err": True, "reason": None}):
            self.assertEqual(dm.process_gate(self.codex), "open_file_check_inconclusive")
        with mock.patch.object(dm.shutil, "which", return_value="/fixture/lsof"), mock.patch.object(dm, "run_command", return_value={"code": 0, "out": "p123\n", "err": False, "reason": None}):
            self.assertEqual(dm.process_gate(self.codex), "open_files_or_working_directory")

    def test_read_only_scan_does_not_create_state(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = dm.main(["--codex-home", str(self.codex), "--state-dir", str(self.store.root), "scan", "--root", str(self.codex)])
        self.assertEqual(code, 0)
        self.assertFalse(self.store.root.exists())

    def test_snapshot_rotation_and_total_budget(self):
        with self.store.lock():
            for i in range(33):
                self.store.write("scan-%02d.json" % i, {"i": i})
            self.assertLessEqual(len(list(self.store.root.glob("scan-*.json"))), 30)
            with mock.patch.object(dm, "MAX_STATE", 100):
                self.store.write("result-large.json", {"data": "x" * 70})
            total = sum(p.stat().st_size for p in self.store.root.iterdir())
            self.assertLessEqual(total, 100)

    def test_each_adapter_executes_only_its_fixture_cache(self):
        for tool in dm.TOOLS:
            with self.subTest(tool=tool), self.fake_tool(tool) as (cache, exe, events):
                with mock.patch.dict(os.environ, {"DISK_MAINTENANCE_UV_NO_SYMLINK_DEPENDENCIES": "1"}):
                    plan = self.cache_plan()
                    self.assertEqual([i["scope"] for i in plan["items"]], [tool])
                    with mock.patch.object(dm, "process_gate", return_value=None):
                        result = dm.apply_plan(plan, self.codex, self.store, [tool])
                self.assertEqual(result["items"][0]["status"], "completed")
                self.assertFalse((cache / "package.whl").exists())

    def test_tool_replaced_after_plan_and_timeout(self):
        with self.fake_tool() as (cache, exe, events):
            plan = self.cache_plan()
            exe.write_text(exe.read_text() + "\n# changed\n")
            with mock.patch.object(dm, "process_gate", return_value=None):
                result = dm.apply_plan(plan, self.codex, self.store, ["pip"])
            self.assertEqual(result["items"][0]["reason"], "tool_cache_binding_changed")
            plan = self.cache_plan()
            original = dm.run_command
            def timed_out(argv, timeout=10):
                if "purge" in argv:
                    return {"code": -15, "out": "", "err": False, "reason": "timeout"}
                return original(argv, timeout)
            with mock.patch.object(dm, "process_gate", return_value=None), mock.patch.object(dm, "run_command", side_effect=timed_out):
                result = dm.apply_plan(plan, self.codex, self.store, ["pip"])
            self.assertEqual(result["items"][0]["status"], "possibly_partial")
            self.assertTrue(result["stopped_early"])

    def test_new_file_after_rename_is_caught_even_if_activity_check_says_idle(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        def late_file(root, tool=None):
            if Path(root).name.startswith(".pending-"):
                (Path(root) / "late-user-result").write_text("preserve")
            return None
        with mock.patch.object(dm, "process_gate", side_effect=late_file):
            result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertEqual(result["items"][0]["status"], "skipped")
        self.assertTrue((path / "late-user-result").exists())

    def test_verified_removal_refuses_new_or_changed_contents(self):
        root = self.base / "verified"
        root.mkdir()
        original = root / "original"
        original.write_text("old")
        scanner = dm.Scanner()
        scanner.measure(root)
        original.write_text("new contents")
        with self.assertRaises(dm.Refusal):
            dm.remove_verified_tree(root, scanner.nodes)
        self.assertEqual(original.read_text(), "new contents")
        scanner = dm.Scanner()
        scanner.measure(root)
        (root / "late").write_text("keep")
        with self.assertRaises(dm.Refusal):
            dm.remove_verified_tree(root, scanner.nodes)
        self.assertTrue((root / "late").exists())

    def test_audit_write_failure_after_cleanup_still_returns_measurements(self):
        _, path = self.aged_scratch()
        plan = self.scratch_plan()
        original = self.store.write
        def fail_final_record(name, data, keep=None):
            if name.startswith("result-") and data.get("items") and data["items"][0]["status"] == "completed":
                raise OSError(28, "No space")
            return original(name, data, keep)
        with mock.patch.object(dm, "process_gate", return_value=None), mock.patch.object(self.store, "write", side_effect=fail_final_record):
            result = dm.apply_plan(plan, self.codex, self.store, ["scratch"])
        self.assertFalse(path.exists())
        self.assertEqual(result["audit_error"], "OSError")
        self.assertTrue(result["stopped_early"])
        self.assertGreater(result["items"][0]["logical_reduction_bytes"], 0)

    def test_read_only_verification_never_creates_key(self):
        self.store.ensure()
        with self.assertRaises(dm.Refusal):
            self.store.verify({"version": 1, "kind": "scan"}, "scan")
        self.assertFalse((self.store.root / "signing.key").exists())

    def test_cli_saved_scan_diff_plan_and_apply(self):
        _, path = self.aged_scratch()
        global_args = ["--codex-home", str(self.codex), "--state-dir", str(self.store.root)]
        def call(args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = dm.main(global_args + args)
            self.assertEqual(status, 0, output.getvalue())
            return json.loads(output.getvalue())
        a = call(["scan", "--root", str(path), "--save-baseline"])
        (path / "more").write_text("extra")
        b = call(["scan", "--root", str(path), "--save-baseline"])
        delta = call(["diff", a["saved_path"], b["saved_path"]])
        self.assertEqual(delta["changes"][0]["logical_delta_bytes"], 5)
        plan = call(["plan", "--scan", b["saved_path"]])
        with mock.patch.object(dm, "process_gate", return_value=None):
            result = call(["apply", "--plan", plan["saved_path"], "--authorize", "scratch"])
        self.assertEqual(result["items"][0]["status"], "completed")

    def test_actual_lsof_detects_open_fixture_file(self):
        if not shutil.which("lsof"):
            self.skipTest("lsof not installed")
        with (self.codex / "open-file").open("w"):
            reason = dm.process_gate(self.codex)
        self.assertIn(reason, ("open_files_or_working_directory", "open_file_check_inconclusive"))

    def test_node_process_in_path_with_spaces_blocks_cache(self):
        clear = {"code": 1, "out": "", "err": False, "reason": None}
        inventory = {"code": 0, "out": "123 /Applications/Tool Box/bin/node\n", "err": False, "reason": None}
        with mock.patch.object(dm.shutil, "which", return_value="/fixture/tool"), mock.patch.object(dm, "run_command", side_effect=[clear, inventory]):
            self.assertEqual(dm.process_gate(self.codex, "npm"), "node_process_may_use_cache")

    def test_candidates_only_preserves_bounds_and_protects_other_roots(self):
        _, path = self.aged_scratch()
        (self.codex / "protected-user-result").write_text("keep")
        doc = dm.scan(self.codex, self.store, discover=False, candidates_only=True)
        self.assertEqual([r["path"] for r in doc["coverage"]], [str(path)])
        self.assertTrue(doc["complete"])
        self.assertEqual(doc["entries_examined"], 2)

    def test_discovered_root_with_symlink_parent_is_not_traversed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "nested").mkdir()
        (outside / "nested/secret").write_text("must not traverse")
        alias = self.base / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        with mock.patch.object(dm, "root_specs", return_value=[{
                "path": str(alias / "nested"), "category": "runtime", "protected": True}]):
            doc = dm.scan(self.codex, self.store, discover=False)
        self.assertFalse(doc["complete"])
        self.assertEqual(doc["entries_examined"], 0)
        self.assertEqual(doc["largest_files"], [])


if __name__ == "__main__":
    unittest.main()
