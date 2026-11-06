import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import disk_maintenance as dm
import iterations as it


class IterationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='iteration-test-')
        self.root=Path(self.tmp.name).resolve()
        self.store=dm.Store(self.root/'state')

    def tearDown(self):
        self.tmp.cleanup()

    def file(self,name,text='content'):
        path=self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
        return str(path)

    def track(self,revision,files,replaces=(),final=False,deps=(),task='task',artifact='report'):
        return it.track(self.store,task,artifact,revision,files,deps,replaces,final,
                        improves=replaces,
                        improvement_evidence='Refined the preceding fixture deliverable' if replaces else None)

    def report(self):
        return it.review(it.load(self.store))['groups'][0]

    def chain(self):
        a=self.file('report_v1.pdf'); b=self.file('report_v2.pdf'); c=self.file('report_v3.pdf')
        self.track('1',[a]); self.track('2',[b],['1']); self.track('3',[c],['2'],True)
        return a,b,c

    def test_inspection_groups_by_directory_and_format_not_mtime(self):
        a=self.file('report_v1.pdf'); b=self.file('report_v2.pdf')
        os.utime(a,(2000000000,2000000000))
        self.file('other/report_v9.pdf'); self.file('report_v3.docx')
        report=it.inspect(self.root)
        self.assertEqual(len(report['families']),1)
        family=report['families'][0]
        self.assertEqual(family['suggested_latest'],b)
        self.assertFalse(family['deletion_authorized'])
        self.assertFalse(self.store.root.exists())

    def test_ambiguous_final_name_or_number_tie_never_selects_winner(self):
        self.file('a_v1.pdf'); self.file('a_final.pdf')
        self.file('b_v01.pdf'); self.file('b_v1.pdf')
        self.file('c.pdf'); self.file('c_v2.pdf')
        for family in it.inspect(self.root)['families']:
            self.assertIsNone(family['suggested_latest'])

    def test_explicit_final_chain_reclaims_only_predecessors(self):
        a,b,c=self.chain()
        draft=self.file('report_v4.pdf')
        self.track('4',[draft])
        group=self.report()
        self.assertEqual({p['path'] for p in group['candidates']},{a,b})
        with mock.patch.object(dm,'process_gate',return_value=None):
            result=it.prune(self.store,'task','report')
        self.assertEqual([p['status'] for p in result['items']],['removed','removed'])
        self.assertFalse(Path(a).exists()); self.assertFalse(Path(b).exists())
        self.assertTrue(Path(c).exists()); self.assertTrue(Path(draft).exists())

    def test_final_bundle_and_old_source_dependencies_are_retained(self):
        a=self.file('plot_v1.svg'); png=self.file('plot_v2.png'); svg=self.file('plot_v2.svg')
        self.track('1',[a]); self.track('2',[png,svg],['1'],True,[a])
        self.assertFalse(self.report()['candidates'])
        self.assertEqual(len(self.report()['retained']),3)

    def test_shared_dependency_across_tasks_is_retained(self):
        a,b,c=self.chain()
        x=self.file('another.pdf')
        self.track('1',[x],final=True,deps=[a],task='other',artifact='other')
        group=it.review(it.load(self.store),'task','report')['groups'][0]
        self.assertEqual([p['path'] for p in group['candidates']],[b])

    def test_missing_or_changed_final_blocks_all_predecessors(self):
        a,b,c=self.chain()
        Path(c).write_text('late edit')
        self.assertFalse(self.report()['candidates'])
        Path(c).unlink()
        with self.assertRaises(dm.Refusal): it.prune(self.store,'task','report')
        self.assertTrue(Path(a).exists())

    def test_changed_old_output_is_not_deleted(self):
        a,b,c=self.chain()
        Path(a).write_text('user made an important edit')
        self.assertEqual([p['path'] for p in self.report()['candidates']],[b])

    def test_unknown_parent_and_revision_overwrite_refused(self):
        a=self.file('a.pdf')
        with self.assertRaises(dm.Refusal): self.track('1',[a],['unknown'])
        self.track('1',[a])
        with self.assertRaises(dm.Refusal): self.track('1',[a],final=True)

    def test_no_final_means_no_cleanup_and_tampering_refused(self):
        a=self.file('a.pdf'); b=self.file('b.pdf')
        self.track('1',[a]); self.track('2',[b],['1'])
        self.assertFalse(self.report()['candidates'])
        registry=dm.read_json(self.store.root/it.REGISTRY)
        registry['groups']={}
        (self.store.root/it.REGISTRY).write_text(__import__('json').dumps(registry))
        with self.assertRaises(dm.Refusal): it.load(self.store)

    def test_active_files_and_unwritable_audit_prevent_deletion(self):
        a,b,c=self.chain()
        with mock.patch.object(dm,'process_gate',return_value='open_files'):
            with self.assertRaises(dm.Refusal): it.prune(self.store,'task','report')
        with mock.patch.object(dm,'process_gate',return_value=None),mock.patch.object(self.store,'write',side_effect=OSError(28,'full')):
            with self.assertRaises(OSError): it.prune(self.store,'task','report')
        self.assertTrue(Path(a).exists()); self.assertTrue(Path(b).exists())

    def test_protected_memory_file_never_pruned(self):
        a=self.file('memory.sqlite'); b=self.file('new.pdf')
        self.track('1',[a]); self.track('2',[b],['1'],True)
        with mock.patch.object(dm,'process_gate',return_value=None):
            with self.assertRaises(dm.Refusal): it.prune(self.store,'task','report')
        self.assertTrue(Path(a).exists())

    def test_symlinks_rejected_and_partial_scan_marked(self):
        a=self.file('a_v1.pdf'); self.file('a_v2.pdf')
        link=self.root/'alias.pdf'; link.symlink_to(a)
        with self.assertRaises(dm.Refusal): self.track('1',[str(link)])
        self.assertFalse(it.inspect(self.root,max_entries=1)['complete'])

    def test_single_notes_path_is_stable_and_mutable(self):
        a,b,c=self.chain()
        notes=self.file('经验记录.md','confirmed lesson')
        it.bind_notes(self.store,'task',notes)
        Path(notes).write_text('revised confirmed lesson')
        it.bind_notes(self.store,'task',notes)
        with self.assertRaises(dm.Refusal):
            it.bind_notes(self.store,'task',self.file('经验记录_v2.md'))
        with mock.patch.object(dm,'process_gate',return_value=None):
            result=it.prune(self.store,'task','report')
        self.assertEqual(len(result['items']),2)
        self.assertEqual(Path(notes).read_text(),'revised confirmed lesson')

    def test_missing_notes_blocks_closeout_cleanup(self):
        a,b,c=self.chain()
        notes=self.file('经验记录.md')
        it.bind_notes(self.store,'task',notes)
        Path(notes).unlink()
        with self.assertRaises(dm.Refusal):it.prune(self.store,'task','report')
        self.assertTrue(Path(a).exists())

    def test_notes_path_protected_even_if_previously_registered_as_output(self):
        notes=self.file('经验记录.md')
        new=self.file('final.md')
        self.track('1',[notes]);self.track('2',[new],['1'],True)
        it.bind_notes(self.store,'task',notes)
        self.assertFalse(self.report()['candidates'])

    def test_unverified_replacement_chain_stays_protected(self):
        paths=[self.file('report_v'+str(n)+'.pdf') for n in range(1,4)]
        for n,path in enumerate(paths,1):
            it.track(self.store,'task','report',str(n),[path],
                     replaces=[str(n-1)] if n>1 else [],final=True,chat='chat')
        self.assertFalse(self.report()['candidates'])
        with mock.patch.object(dm,'process_gate',return_value=None):
            result=it.prune(self.store,'task','report')
            reminder=it.remind(self.store,'task','chat')
        self.assertEqual(result['items'],[])
        self.assertEqual(reminder['status'],'not_due')
        self.assertTrue(all(Path(p).exists() for p in paths))

    def test_improvement_evidence_required_and_unknown_predecessor_rejected(self):
        original=self.file('report_v1.pdf')
        refined=self.file('report_v2.pdf')
        it.track(self.store,'task','report','1',[original])
        for evidence in (None,'',' \t\n','x'*1001):
            with self.subTest(evidence_length=len(evidence) if evidence is not None else None):
                with self.assertRaises(dm.Refusal):
                    it.track(self.store,'task','report','2',[refined],
                             improves=['1'],improvement_evidence=evidence)
        with self.assertRaises(dm.Refusal):
            it.track(self.store,'task','report','2',[refined],
                     improves=['missing'],improvement_evidence='Adjusted the original layout')
        with self.assertRaises(dm.Refusal):
            it.track(self.store,'task','report','2',[refined],
                     improvement_evidence='No actual predecessor was supplied')
        self.assertNotIn('2',it.load(self.store)['groups'][it.group_key('task','report')]['revisions'])

    def test_improves_adds_predecessor_without_redundant_replaces_flag(self):
        original=self.file('report_v1.pdf','Original result with incorrect units')
        refined=self.file('report_v2.pdf','Corrected units and revised explanatory text')
        it.track(self.store,'task','report','1',[original])
        it.track(self.store,'task','report','2',[refined],final=True,
                 improves=['1'],improvement_evidence='Corrected unit labels in the existing report')
        record=it.load(self.store)['groups'][it.group_key('task','report')]['revisions']['2']
        self.assertIn('1',record['replaces'])
        self.assertEqual([p['path'] for p in self.report()['candidates']],[original])

    def test_new_content_and_alternative_final_do_not_discard_original(self):
        # Names, format, directory, and delivery order cannot prove the same
        # content was improved. These are independently useful deliverables.
        original=self.file('report_v1.pdf','Sales review for Q1')
        new_content=self.file('report_v2.pdf','Maintenance manual for a laboratory instrument')
        alternative=self.file('report_final.pdf','Alternative proposal retaining a different method')
        it.track(self.store,'task','report','1',[original],final=True)
        it.track(self.store,'task','report','2',[new_content],replaces=['1'],final=True)
        it.track(self.store,'task','report','3',[alternative],replaces=['2'],final=True)
        self.assertFalse(self.report()['candidates'])
        with mock.patch.object(dm,'process_gate',return_value=None):
            self.assertEqual(it.prune(self.store,'task','report')['items'],[])
        self.assertTrue(all(Path(p).exists() for p in (original,new_content,alternative)))

    def test_verified_lineage_stops_at_unknown_edge(self):
        a=self.file('report_v1.pdf','Independent initial topic')
        b=self.file('report_v2.pdf','New report topic')
        c=self.file('report_v3.pdf','Corrected chart labels in the new report')
        it.track(self.store,'task','report','1',[a])
        it.track(self.store,'task','report','2',[b],replaces=['1'])
        it.track(self.store,'task','report','3',[c],final=True,
                 improves=['2'],improvement_evidence='Corrected labels in revision 2')
        self.assertEqual([p['path'] for p in self.report()['candidates']],[b])
        with mock.patch.object(dm,'process_gate',return_value=None):
            result=it.prune(self.store,'task','report')
        self.assertEqual([p['path'] for p in result['items']],[b])
        self.assertTrue(Path(a).exists()); self.assertTrue(Path(c).exists())

    def test_modified_content_is_a_valid_improvement_while_other_branch_is_retained(self):
        original=self.file('report_v1.pdf','Known totals: 10\nChart label: old')
        refined=self.file('report_v2.pdf','Known totals: 12\nChart label: corrected')
        final=self.file('report_v3.pdf','Known totals: 12\nChart label: corrected\nFootnote added')
        independent=self.file('report_blue_option.pdf','Independent design using a different dataset')
        it.track(self.store,'task','report','1',[original])
        it.track(self.store,'task','report','blue',[independent],final=True)
        it.track(self.store,'task','report','2',[refined],improves=['1'],
                 improvement_evidence='Corrected totals and label in the original report')
        it.track(self.store,'task','report','3',[final],final=True,improves=['2'],
                 improvement_evidence='Added the requested footnote to revision 2')
        self.assertNotEqual(Path(original).read_bytes(),Path(refined).read_bytes())
        self.assertEqual({p['path'] for p in self.report()['candidates']},{original,refined})
        with mock.patch.object(dm,'process_gate',return_value=None):
            it.prune(self.store,'task','report')
        self.assertFalse(Path(original).exists()); self.assertFalse(Path(refined).exists())
        self.assertTrue(Path(final).exists()); self.assertTrue(Path(independent).exists())


if __name__=='__main__': unittest.main()
