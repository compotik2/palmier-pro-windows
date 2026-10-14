import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from palmier.model import Editor
from palmier.media import executable, probe, render, ExportQueue, run


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="palmier-test-")
        self.root=Path(self.temp.name)
        self.red=self.root/"red clip — Unicode.mp4"
        run([executable("ffmpeg"),"-v","error","-y","-f","lavfi","-i","color=red:s=320x180:r=30:d=2",
             "-f","lavfi","-i","sine=frequency=440:duration=2","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(self.red)],timeout=30)
        self.e=Editor()
        self.e.new(fps=30,width=320,height=180)
        self.m=probe(self.red)
        self.e.import_entry(self.m)
        self.e.add_track("video")
        self.cid=self.e.add_clips([dict(mediaRef=self.m["id"],trackIndex=0,startFrame=0,endFrame=60)])["clipIds"][0]

    def tearDown(self):
        self.temp.cleanup()

    def pixel(self,file,seconds):
        data=run([executable("ffmpeg"),"-v","error","-ss",str(seconds),"-i",str(file),"-frames:v","1","-vf","scale=1:1","-f","rawvideo","-pix_fmt","rgb24","pipe:1"],timeout=30).stdout
        return tuple(data[:3])

    def test_real_export_duration_audio_and_red_pixels(self):
        output=self.root/"export.mp4"
        result=render(self.e,self.e.timeline,output)
        self.assertEqual(result["encoder"],"libx264")
        info=probe(output)
        self.assertAlmostEqual(info["duration"],2,delta=.1)
        self.assertTrue(info["hasAudio"])
        r,g,b=self.pixel(output,.5)
        self.assertGreater(r,200)
        self.assertLess(g,30)
        self.assertLess(b,30)

    def test_gap_is_black_and_timeline_source_trim(self):
        self.e.move([dict(clipId=self.cid,toFrame=30)])
        output=self.root/"gap.mp4"
        render(self.e,self.e.timeline,output)
        self.assertLess(max(self.pixel(output,.3)),20)
        self.assertGreater(self.pixel(output,1.5)[0],200)

    def test_frame_seek_and_text_overlay_real_pixels(self):
        self.e.add_texts([dict(startFrame=0,endFrame=60,content="Windows text: 100% 'safe'",style=dict(fontSize=32,color="#FFFFFF"))])
        output=self.root/"frame.png"
        render(self.e,self.e.timeline,output,frame=15)
        self.assertEqual(probe(output)["type"],"image")
        pixels=run([executable("ffmpeg"),"-v","error","-i",str(output),"-f","rawvideo","-pix_fmt","rgb24","pipe:1"],timeout=30).stdout
        self.assertTrue(any(pixels[i]>220 and pixels[i+1]>220 and pixels[i+2]>220 for i in range(0,len(pixels)-2,3)))

    def test_image_and_audio_tracks_mix(self):
        image=self.root/"image.png"
        audio=self.root/"audio.wav"
        run([executable("ffmpeg"),"-v","error","-y","-f","lavfi","-i","color=blue:s=320x180","-frames:v","1",str(image)],timeout=30)
        run([executable("ffmpeg"),"-v","error","-y","-f","lavfi","-i","sine=frequency=880:duration=2",str(audio)],timeout=30)
        for file in (image,audio):
            self.e.import_entry(probe(file))
        image_ref=self.e.manifest["entries"][1]["id"]
        audio_ref=self.e.manifest["entries"][2]["id"]
        self.e.add_clips([dict(mediaRef=image_ref,startFrame=0,endFrame=60)])
        self.e.add_clips([dict(mediaRef=audio_ref,startFrame=0,endFrame=60)])
        output=self.root/"mixed.mp4"
        render(self.e,self.e.timeline,output)
        self.assertTrue(probe(output)["hasAudio"])
        raw=run([executable("ffmpeg"),"-v","error","-i",str(output),"-map","0:a","-f","s16le","pipe:1"],timeout=30).stdout
        self.assertTrue(any(raw))

    def test_unsupported_effect_does_not_replace_existing_export(self):
        self.e.clip(self.cid)[1]["effects"]=[dict(type="notImplemented")]
        output=self.root/"keep.mp4"
        output.write_bytes(b"original")
        with self.assertRaises(ValueError):
            render(self.e,self.e.timeline,output)
        self.assertEqual(output.read_bytes(),b"original")

    def test_missing_media_reports_error(self):
        self.red.unlink()
        with self.assertRaisesRegex(ValueError,"Missing media"):
            render(self.e,self.e.timeline,self.root/"missing.mp4")

    def test_precancel_does_not_create_output(self):
        cancel=threading.Event()
        cancel.set()
        output=self.root/"cancel.mp4"
        with self.assertRaisesRegex(RuntimeError,"Cancelled"):
            render(self.e,self.e.timeline,output,cancel=cancel)
        self.assertFalse(output.exists())

    def test_hardware_attempt_has_software_fallback(self):
        output=self.root/"fallback.mp4"
        result=render(self.e,self.e.timeline,output,hardware=True)
        self.assertIn(result["encoder"],("h264_nvenc","libx264"))
        self.assertGreater(output.stat().st_size,1000)

    def test_real_ffmpeg_encoder_failure_falls_back_to_software(self):
        from unittest.mock import patch
        original=subprocess.Popen
        def unavailable_hardware(command,*args,**kwargs):
            command=list(command)
            if "h264_nvenc" in command:
                command[command.index("h264_nvenc")]="deliberately_unavailable_encoder"
            return original(command,*args,**kwargs)
        output=self.root/"forced-fallback.mp4"
        with patch("palmier.media.subprocess.Popen",side_effect=unavailable_hardware):
            result=render(self.e,self.e.timeline,output,hardware=True)
        self.assertEqual(result["encoder"],"libx264")
        self.assertTrue(result["softwareFallback"])
        self.assertGreater(output.stat().st_size,1000)

    def test_export_queue_progress_completion_and_readback(self):
        queue=ExportQueue(self.e)
        job=queue.start(dict(outputPath=str(self.root/"queued.mp4")))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            current=queue.list()[0]
            if current["status"] not in ("queued","running"):
                break
            time.sleep(.05)
        self.assertEqual(current["status"],"done",current)
        self.assertEqual(current["progress"],100)
        self.assertTrue(Path(job["path"]).exists())

    def test_h265_and_720p_export(self):
        output=self.root/"hevc.mp4"
        render(self.e,self.e.timeline,output,codec="H.265",resolution="720p",bitrate=2)
        info=probe(output)
        self.assertEqual((info["sourceWidth"],info["sourceHeight"]),(1280,720))
        import json
        streams=json.loads(run([executable("ffprobe"),"-v","error","-show_streams","-of","json",str(output)]).stdout)["streams"]
        self.assertEqual(next(s["codec_name"] for s in streams if s["codec_type"]=="video"),"hevc")

    def test_1080p_and_4k_export(self):
        self.e.properties([self.cid],dict(durationFrames=3))
        for resolution,height in [("1080p",1080),("4K",2160)]:
            with self.subTest(resolution=resolution):
                output=self.root/(resolution+".mp4")
                render(self.e,self.e.timeline,output,resolution=resolution,bitrate=2)
                info=probe(output)
                self.assertEqual((info["sourceWidth"],info["sourceHeight"]),(round(height*16/9),height))

    def test_mov_mkv_mp3_jpg_import(self):
        for suffix in (".mov",".mkv"):
            dest=self.root/("sample"+suffix)
            run([executable("ffmpeg"),"-v","error","-y","-i",str(self.red),"-c","copy",str(dest)],timeout=30)
            self.assertEqual(probe(dest)["type"],"video")
        mp3=self.root/"sample.mp3"
        run([executable("ffmpeg"),"-v","error","-y","-i",str(self.red),"-vn","-c:a","libmp3lame",str(mp3)],timeout=30)
        self.assertEqual(probe(mp3)["type"],"audio")
        jpg=self.root/"sample.jpg"
        run([executable("ffmpeg"),"-v","error","-y","-i",str(self.red),"-frames:v","1",str(jpg)],timeout=30)
        self.assertEqual(probe(jpg)["type"],"image")

    def test_fade_and_muted_audio_render_values(self):
        self.e.properties([self.cid],dict(fadeInFrames=30))
        self.e.timeline["tracks"][0]["muted"]=True
        output=self.root/"fade.mp4"
        render(self.e,self.e.timeline,output)
        first=self.pixel(output,.1)[0]
        last=self.pixel(output,1.5)[0]
        self.assertLess(first,last*.4)
        import array
        raw=run([executable("ffmpeg"),"-v","error","-i",str(output),"-map","0:a","-f","s16le","pipe:1"],timeout=30).stdout
        samples=array.array("h",raw)
        self.assertLess(max(abs(s) for s in samples),32)

    def test_cancelled_queued_job_never_replaces_output(self):
        output=self.root/"keep.mp4"
        output.write_bytes(b"keep")
        queue=ExportQueue(self.e)
        queue.gate.acquire()
        job=queue.start(dict(outputPath=str(output)))
        queue.cancel(job["jobId"])
        queue.gate.release()
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and queue.list()[0]["status"]=="queued":
            time.sleep(.02)
        self.assertEqual(queue.list()[0]["status"],"cancelled")
        self.assertEqual(output.read_bytes(),b"keep")


if __name__=="__main__":
    unittest.main()
