import copy
import json
import tempfile
import unittest
from pathlib import Path
from palmier.model import Editor, end


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.e=Editor()
        self.e.new(fps=30,width=320,height=180)
        self.e.import_entry(dict(id="a",name="sample",type="video",duration=10,hasAudio=False,
                                 source={"external":{"absolutePath":"C:/missing.mov"}}))
        self.e.add_track("video")

    def add(self,start=0,finish=90):
        return self.e.add_clips([dict(mediaRef="a",trackIndex=0,startFrame=start,endFrame=finish)])["clipIds"][0]

    def test_overwrite_preserves_left_and_right_source_offsets(self):
        original=self.add(0,90)
        self.add(30,60)
        clips=sorted(self.e.timeline["tracks"][0]["clips"],key=lambda c:c["startFrame"])
        self.assertEqual([(c["startFrame"],end(c),c["trimStartFrame"]) for c in clips],[(0,30,0),(30,60,0),(60,90,60)])
        self.assertEqual(clips[0]["id"],original)

    def test_split_end_exclusive_offsets_and_undo_redo(self):
        cid=self.add()
        before=self.e.snapshot()
        right=self.e.split([dict(clipId=cid,atFrame=30)])["newClipIds"][0]
        self.assertEqual(self.e.clip(cid)[1]["durationFrames"],30)
        self.assertEqual(self.e.clip(right)[1]["trimStartFrame"],30)
        split=self.e.snapshot()
        self.e.undo()
        self.assertEqual(self.e.snapshot(),before)
        self.e.undo(True)
        self.assertEqual(self.e.snapshot(),split)

    def test_failed_batch_restores_state_and_history(self):
        cid=self.add()
        before=self.e.snapshot()
        count=len(self.e.undo_stack)
        with self.assertRaises(ValueError):
            self.e.move([dict(clipId=cid,toFrame=60),dict(clipId="missing",toFrame=10)])
        self.assertEqual(self.e.snapshot(),before)
        self.assertEqual(len(self.e.undo_stack),count)

    def test_nested_ui_edit_has_one_undo_entry(self):
        cid=self.add()
        before=self.e.snapshot()
        count=len(self.e.undo_stack)
        def action():
            self.e.properties([cid],dict(durationFrames=60))
            self.e.move([dict(clipId=cid,toFrame=30)])
        self.e.mutate("trim",action)
        self.assertEqual(len(self.e.undo_stack),count+1)
        self.e.undo()
        self.assertEqual(self.e.snapshot(),before)

    def test_noop_does_not_create_history(self):
        cid=self.add()
        count=len(self.e.undo_stack)
        self.e.properties([cid],dict(opacity=1))
        self.assertEqual(len(self.e.undo_stack),count)

    def test_nonfinite_speed_invalid_duration_and_source_bounds(self):
        cid=self.add()
        for values in [dict(speed=float("nan")),dict(durationFrames=0),dict(durationFrames=400),dict(trimStartFrame=-1),dict(opacity=2),dict(fadeInFrames=91)]:
            before=self.e.snapshot()
            with self.assertRaises(ValueError):
                self.e.properties([cid],values)
            self.assertEqual(self.e.snapshot(),before)

    def test_save_load_preserves_original_unknown_fields(self):
        self.add()
        self.e.doc["speakers"]=[dict(id=1,name="Person",centroid=[.1,.2])]
        self.e.timeline["tracks"][0]["clips"][0]["futureField"]={"opaque":123}
        with tempfile.TemporaryDirectory() as root:
            package=Path(root)/"Unicode — project.palmier"
            self.e.save(package)
            reopened=Editor()
            reopened.load(package)
            self.assertEqual(reopened.snapshot(),self.e.snapshot())
            self.assertFalse(reopened.dirty)

    def test_malformed_load_leaves_active_project_unchanged(self):
        before=self.e.snapshot()
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/"project.json").write_text('{"timelines": []}')
            with self.assertRaises(ValueError):
                self.e.load(root)
        self.assertEqual(self.e.snapshot(),before)

    def test_save_as_existing_directory_refused(self):
        with tempfile.TemporaryDirectory(suffix=".palmier") as root:
            with self.assertRaises(ValueError):
                self.e.save(root)

    def test_save_as_rebases_package_media(self):
        with tempfile.TemporaryDirectory() as root:
            first=Path(root)/"first.palmier"
            self.e.save(first)
            (first/"media"/"a.mov").write_bytes(b"test-source")
            self.e.manifest["entries"][0]["source"]={"project":{"relativePath":"media/a.mov"}}
            self.e.save()
            second=Path(root)/"second.palmier"
            self.e.save(second)
            self.assertEqual((second/"media"/"a.mov").read_bytes(),b"test-source")

    def test_package_traversal_refused(self):
        with tempfile.TemporaryDirectory() as root:
            self.e.package=Path(root)
            with self.assertRaises(ValueError):
                self.e.media_path(dict(id="bad",source={"project":{"relativePath":"../private"}}))

    def test_save_allows_edits_and_keeps_later_changes_dirty(self):
        import threading
        import shutil
        from unittest.mock import patch
        cid=self.add()
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/"concurrent.palmier"
            self.e.save(target)
            started,release,edited=threading.Event(),threading.Event(),threading.Event()
            original=shutil.copytree
            def gated(*args,**kwargs):
                started.set()
                if not release.wait(5):
                    raise RuntimeError("test gate timeout")
                return original(*args,**kwargs)
            errors=[]
            def saving():
                try:
                    self.e.save()
                except Exception as error:
                    errors.append(error)
            with patch("palmier.model.shutil.copytree",side_effect=gated):
                worker=threading.Thread(target=saving)
                worker.start()
                self.assertTrue(started.wait(2))
                def editing():
                    self.e.properties([cid],dict(opacity=.3))
                    edited.set()
                edit=threading.Thread(target=editing)
                edit.start()
                succeeded=edited.wait(2)
                release.set()
                worker.join(5)
                edit.join(5)
            self.assertTrue(succeeded,"File work blocked the editor state owner")
            self.assertEqual(errors,[])
            self.assertTrue(self.e.dirty)
            loaded=Editor()
            loaded.load(target)
            self.assertEqual(loaded.clip(cid)[1]["opacity"],1)
            self.assertEqual(self.e.clip(cid)[1]["opacity"],.3)

    def test_stale_project_open_refuses_to_discard_new_edits(self):
        cid=self.add()
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/"p.palmier"
            self.e.save(target)
            old_revision=self.e.revision
            self.e.properties([cid],dict(opacity=.5))
            with self.assertRaisesRegex(ValueError,"active project changed"):
                self.e.load(target,expected_revision=old_revision)
            self.assertEqual(self.e.clip(cid)[1]["opacity"],.5)


if __name__=="__main__":
    unittest.main()
