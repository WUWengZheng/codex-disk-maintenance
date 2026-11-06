"""End-to-end safety cases for chat-bound, one-shot cleanup suggestions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import disk_maintenance as dm
import iterations as it


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='reminder-test-')
        self.root = Path(self.tmp.name).resolve()
        self.store = dm.Store(self.root / 'state')
        self.gate = mock.patch.object(dm, 'process_gate', return_value=None)
        self.gate.start()

    def tearDown(self):
        self.gate.stop()
        self.tmp.cleanup()

    def file(self, name, text='content'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return str(path)

    def revision(self, n, chat='chat', artifact='report', final=True, deps=(), suffix='.pdf', task='task'):
        path = self.file(artifact + '_v' + str(n) + suffix)
        predecessor = [str(n - 1)] if n > 1 else []
        it.track(self.store, task, artifact, str(n), [path], deps,
                 predecessor, final, chat, improves=predecessor,
                 improvement_evidence='Refined the preceding fixture deliverable' if predecessor else None)
        return path

    def chain(self, artifact='report', chat='chat', task='task'):
        return [self.revision(n, chat=chat, artifact=artifact, task=task) for n in range(1, 4)]

    def offer(self, chat='chat', task='task'):
        result = it.remind(self.store, task, chat)
        self.assertEqual(result['status'], 'offered', result)
        return result['offer']['offer_id']

    def notes(self):
        path = self.file('经验记录.md', 'One confirmed useful lesson')
        it.bind_notes(self.store, 'task', path)
        return path

    def test_three_delivered_rounds_offer_once_without_deletion(self):
        self.revision(1); self.revision(2)
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'not_due')
        final = self.revision(3)
        result = it.remind(self.store, 'task', 'chat')
        self.assertEqual(result['status'], 'offered')
        self.assertEqual(result['offer']['file_count'], 2)
        self.assertEqual(result['offer']['logical_bytes'], 2 * len('content'))
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'already_offered')
        self.assertTrue(Path(final).exists())
        self.assertTrue((self.root / 'report_v1.pdf').exists())

    def test_drafts_and_other_chats_do_not_count_as_delivery_rounds(self):
        self.revision(1); self.revision(2, final=False); self.revision(3)
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'not_due')
        self.revision(4, chat='another-chat')
        self.assertEqual(it.remind(self.store, 'task', 'another-chat')['status'], 'not_due')
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'not_due')

    def test_legacy_registrations_have_no_invented_chat_evidence(self):
        self.chain(chat=None)
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'not_due')

    def test_confirmation_preserves_final_sources_notes_and_unrelated_files(self):
        paths = self.chain()
        src = self.file('plot.py', 'print(1)')
        final = self.revision(4, deps=[src])
        unrelated = self.file('independent-draft.pdf')
        offer = self.offer()
        notes = self.notes()
        Path(notes).write_text('Updated in the sole original notes file')
        result = it.confirm(self.store, 'chat', offer)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(all(not Path(p).exists() for p in paths))
        self.assertTrue(all(Path(p).exists() for p in [src, final, notes, unrelated]))
        journal = result['results'][0]
        self.assertEqual(len(journal['items']), 3)
        self.assertIn('volumes_before', journal)
        self.assertIn('volumes_after', journal)
        self.assertTrue(all(p['allocated_bytes'] >= 0 for p in journal['items']))
        self.file('report_v1.pdf', 'A new file at a previously removed path')
        with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)
        self.assertTrue((self.root / 'report_v1.pdf').exists())

    def test_decline_suppresses_until_new_delivery(self):
        self.chain()
        offer = self.offer()
        self.assertEqual(it.dismiss(self.store, 'chat', offer)['status'], 'dismissed')
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'already_offered')
        self.revision(4)
        self.assertNotEqual(self.offer(), offer)

    def test_wrong_chat_or_offer_id_never_grants_permission(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        for chat, identifier in [('another-chat', offer), ('chat', 'wrong-id')]:
            with self.assertRaises(dm.Refusal): it.confirm(self.store, chat, identifier)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_candidate_changes_do_not_reoffer_unchanged_deliveries(self):
        self.chain(); other = self.chain(artifact='figure')
        offer = self.offer()
        it.dismiss(self.store, 'chat', offer)
        for p in other[:-1]: Path(p).write_text('User changed an old result')
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'already_offered')

    def test_dedup_survives_switching_tasks_in_same_chat(self):
        self.chain()
        it.dismiss(self.store, 'chat', self.offer())
        self.chain(artifact='figure', task='other-task')
        other = self.offer(task='other-task')
        it.dismiss(self.store, 'chat', other)
        self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'already_offered')

    def test_executing_offer_cannot_be_overwritten_by_new_reminder(self):
        self.chain(); offer = self.offer(); self.notes()
        self.chain(artifact='figure', task='other-task')
        original = it.prune
        observed = []
        def concurrent_check(*args, **kwargs):
            observed.append(it.remind(self.store, 'other-task', 'chat'))
            return original(*args, **kwargs)
        with mock.patch.object(it, 'prune', side_effect=concurrent_check):
            result = it.confirm(self.store, 'chat', offer)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(observed[0]['status'], 'blocked')
        self.assertEqual(it.load(self.store)['reminders']['chat']['offer_id'], offer)

    def test_new_final_invalidates_old_confirmation_and_does_not_expand_it(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        newest = self.revision(4)
        with self.assertRaisesRegex(dm.Refusal, 'offer_changed'):
            it.confirm(self.store, 'chat', offer)
        self.assertTrue(all(Path(p).exists() for p in paths + [newest]))
        fresh = self.offer()
        with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)
        self.assertEqual(it.confirm(self.store, 'chat', fresh)['status'], 'completed')

    def test_candidate_or_final_changes_block_confirmation(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        Path(paths[0]).write_text('User edits must be retained')
        with self.assertRaisesRegex(dm.Refusal, 'offer_changed'):
            it.confirm(self.store, 'chat', offer)
        self.assertTrue(Path(paths[1]).exists())
        Path(paths[-1]).unlink()
        with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)

    def test_expired_offer_does_not_delete_or_repeatedly_prompt(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        with mock.patch.object(it.time, 'time', return_value=time.time() + it.OFFER_SECONDS + 1):
            with self.assertRaisesRegex(dm.Refusal, 'expired'):
                it.confirm(self.store, 'chat', offer)
            self.assertEqual(it.remind(self.store, 'task', 'chat')['status'], 'already_offered')
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_notes_must_be_saved_and_bound_before_confirming(self):
        paths = self.chain(); offer = self.offer()
        with self.assertRaisesRegex(dm.Refusal, 'notes_before'):
            it.confirm(self.store, 'chat', offer)
        notes = self.notes(); Path(notes).unlink()
        with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_active_and_protected_files_do_not_generate_actionable_offer(self):
        self.chain()
        with mock.patch.object(dm, 'process_gate', return_value='open_files'):
            report = it.remind(self.store, 'task', 'chat')
        self.assertEqual(report['status'], 'not_due')
        self.assertEqual(report['blocked'][0]['reason'], 'open_files')
        for n in range(1, 4): self.revision(n, artifact='memory', suffix='.sqlite')
        # The valid report group can be offered; memory is never included.
        report = it.remind(self.store, 'task', 'chat')
        self.assertEqual([s['artifact'] for s in report['offer']['scopes']], ['report'])

    def test_permission_and_audit_failures_before_consumption_leave_files(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        with mock.patch.object(self.store, 'write', side_effect=OSError(28, 'full')):
            with self.assertRaises(OSError): it.confirm(self.store, 'chat', offer)
        with mock.patch.object(dm, 'process_gate', return_value='open_files'):
            with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_signature_and_single_instance_lock_are_enforced(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        with self.store.lock():
            with self.assertRaisesRegex(dm.Refusal, 'lock_busy'):
                it.confirm(self.store, 'chat', offer)
        data = dm.read_json(self.store.root / it.REGISTRY)
        data['reminders']['chat']['scopes'][0]['candidates'] = []
        (self.store.root / it.REGISTRY).write_text(json.dumps(data))
        with self.assertRaisesRegex(dm.Refusal, 'signature'):
            it.confirm(self.store, 'chat', offer)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_multiple_artifacts_are_preflighted_before_any_removal(self):
        a = self.chain(); b = self.chain(artifact='figure')
        offer = self.offer(); self.notes()
        Path(b[-1]).write_text('Late user edit')
        with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)
        self.assertTrue(all(Path(p).exists() for p in a + b))

    def test_partial_execution_is_consumed_and_never_automatically_replayed(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        with mock.patch.object(it, 'prune', side_effect=OSError(28, 'full')):
            result = it.confirm(self.store, 'chat', offer)
        self.assertEqual(result['status'], 'stopped_review_required')
        with self.assertRaises(dm.Refusal): it.confirm(self.store, 'chat', offer)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_change_between_final_check_and_rename_is_preserved(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        original = it.valid
        changed = []
        def edit_after_check(entry):
            result = original(entry)
            # The last check is inside prune, after the offer is consumed.
            state = it.load(self.store)['reminders']['chat']['status']
            if entry['path'] == paths[0] and state == 'executing' and not changed:
                # prepare_prune also checks this path: defer until the audit
                # journal exists so this targets the final deletion check.
                if list(self.store.root.glob('result-iterations-*.json')):
                    Path(paths[0]).write_text('User changed the result during cleanup')
                    changed.append(True)
            return result
        with mock.patch.object(it, 'valid', side_effect=edit_after_check):
            result = it.confirm(self.store, 'chat', offer)
        self.assertEqual(result['status'], 'stopped_review_required')
        self.assertTrue(changed)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_cli_confirmation_requires_explicit_authorization_flag(self):
        paths = self.chain(); offer = self.offer(); self.notes()
        script = str(Path(it.__file__))
        result = subprocess.run([sys.executable, script, '--state-dir', str(self.store.root),
                                 'confirm', '--chat', 'chat', '--offer-id', offer], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--authorize-superseded', result.stderr)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_unrelated_deliveries_do_not_count_toward_improvement_rounds(self):
        a=self.file('report_v1.pdf','Independent first topic')
        b=self.file('report_v2.pdf','A new unrelated topic')
        c=self.file('report_v3.pdf','Refinement of the second topic')
        it.track(self.store,'task','report','1',[a],final=True,chat='chat')
        it.track(self.store,'task','report','2',[b],final=True,chat='chat',replaces=['1'])
        it.track(self.store,'task','report','3',[c],final=True,chat='chat',improves=['2'],
                 improvement_evidence='Corrected the terminology in revision 2')
        result=it.remind(self.store,'task','chat')
        self.assertEqual(result['status'],'not_due')
        d=self.file('report_v4.pdf','Further refinement of the second topic')
        it.track(self.store,'task','report','4',[d],final=True,chat='chat',improves=['3'],
                 improvement_evidence='Improved the existing paragraph layout')
        result=it.remind(self.store,'task','chat')
        self.assertEqual(result['status'],'offered')
        offered={p['path'] for scope in result['offer']['scopes'] for p in scope['candidates']}
        self.assertEqual(offered,{b,c})
        self.notes()
        self.assertEqual(it.confirm(self.store,'chat',result['offer']['offer_id'])['status'],'completed')
        self.assertTrue(Path(a).exists()); self.assertTrue(Path(d).exists())

    def test_unverified_legacy_offer_cannot_be_confirmed_after_upgrade(self):
        paths=self.chain(); offer=self.offer(); self.notes()
        registry=it.load(self.store)
        group=registry['groups'][it.group_key('task','report')]
        # Model a pre-upgrade signed registry which had --replaces links and
        # a pending offer, but no evidence of same-deliverable improvements.
        for record in group['revisions'].values():
            record.pop('improves',None)
            record.pop('improvement_evidence',None)
        self.store.write(it.REGISTRY,self.store.sign(registry))
        with self.assertRaisesRegex(dm.Refusal,'offer_changed'):
            it.confirm(self.store,'chat',offer)
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_cli_records_improvement_evidence_and_rejects_missing_basis(self):
        original=self.file('report_v1.pdf','Original draft')
        revised=self.file('report_v2.pdf','Revised draft with corrected units')
        it.track(self.store,'task','report','1',[original],final=True,chat='chat')
        command=[sys.executable,str(Path(it.__file__)),'--state-dir',str(self.store.root),
                 'track','--task','task','--artifact','report','--revision','2','--file',revised,
                 '--chat','chat','--final','--improves','1']
        refused=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(refused.returncode,2)
        accepted=subprocess.run(command+['--improvement-evidence','Corrected unit labels in the original draft'],
                                capture_output=True,text=True)
        self.assertEqual(accepted.returncode,0,accepted.stdout+accepted.stderr)
        record=it.load(self.store)['groups'][it.group_key('task','report')]['revisions']['2']
        self.assertEqual(record['improves'],['1'])
        self.assertIn('1',record['replaces'])
        self.assertEqual(record['improvement_evidence'],'Corrected unit labels in the original draft')


if __name__ == '__main__':
    unittest.main()
