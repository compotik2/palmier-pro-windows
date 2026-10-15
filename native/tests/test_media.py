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

    def test_export_refuses_to_replace_source_media(self):
        before=self.red.read_bytes()
        with self.assertRaisesRegex(ValueError,"source media"):
            render(self.e,self.e.timeline,self.red)
        self.assertEqual(self.red.read_bytes(),before)

    def test_no_overwrite_preserves_file_created_during_render(self):
        output=self.root/"race.mp4"
        queue=ExportQueue(self.e)
        original=queue.patch
        def competing_writer(job,**values):
            if values.get("progress",0)>0 and not output.exists():
                output.write_bytes(b"other writer")
            original(job,**values)
        queue.patch=competing_writer
        queue.start(dict(outputPath=str(output),overwrite=False))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline and queue.list()[0]["status"] in ("queued","running"):
            time.sleep(.02)
        self.assertEqual(queue.list()[0]["status"],"failed")
        self.assertEqual(output.read_bytes(),b"other writer")

    def test_mp3_album_art_is_audio_not_a_video_track(self):
        cover=self.root/"cover.jpg"
        run([executable("ffmpeg"),"-v","error","-y","-i",str(self.red),"-frames:v","1",str(cover)],timeout=30)
        output=self.root/"album.mp3"
        run([executable("ffmpeg"),"-v","error","-y","-i",str(self.red),"-i",str(cover),
             "-map","0:a","-map","1:v","-c:a","libmp3lame","-c:v","copy","-id3v2_version","3",str(output)],timeout=30)
        info=probe(output)
        self.assertEqual(info["type"],"audio")
        self.assertEqual(info["sourceWidth"],0)
        self.assertTrue(info["hasAudio"])

    def test_unit_speed_preserves_music_waveform_alignment(self):
        import array,math,wave
        rate=44100
        music=self.root/"chirp.wav"
        samples=array.array("h",(round(13000*(math.sin(2*math.pi*(130*(i/rate)+170*(i/rate)**2))+.35*math.sin(2*math.pi*530*(i/rate)))) for i in range(rate*2)))
        with wave.open(str(music),"wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(rate)
            file.writeframes(samples.tobytes())
        m=probe(music)
        self.e.import_entry(m)
        self.e.timeline["tracks"][0]["muted"]=True
        self.e.add_clips([dict(mediaRef=m["id"],startFrame=0,endFrame=60)])
        output=self.root/"identity-audio.mp4"
        render(self.e,self.e.timeline,output)
        def decode(path):
            raw=run([executable("ffmpeg"),"-v","error","-i",str(path),"-map","0:a:0","-ac","1","-ar","48000","-f","f32le","pipe:1"],timeout=30).stdout
            return array.array("f",raw)
        a,b=decode(music),decode(output)
        n=min(len(a),len(b))
        correlation=sum(a[i]*b[i] for i in range(n))/math.sqrt(sum(v*v for v in a[:n])*sum(v*v for v in b[:n]))
        self.assertGreater(correlation,.98)

    def test_split_video_audio_graph_finishes(self):
        self.e.split([dict(clipId=self.cid,atFrame=30)])
        cancel=threading.Event()
        timer=threading.Timer(20,cancel.set)
        timer.start()
        try:
            output=self.root/"split-audio.mp4"
            render(self.e,self.e.timeline,output,cancel=cancel)
            self.assertAlmostEqual(probe(output)["duration"],2,delta=.1)
        finally:
            timer.cancel()

    def test_aac_encoder_priming_is_preserved_at_zero_source_trim(self):
        import array,math,wave
        rate=44100
        wave_path=self.root/"source-wave.wav"
        samples=array.array("h",(round(14000*math.sin(2*math.pi*(170*(i/rate)+210*(i/rate)**2))) for i in range(rate*2)))
        with wave.open(str(wave_path),"wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(rate)
            file.writeframes(samples.tobytes())
        encoded=self.root/"primed.m4a"
        run([executable("ffmpeg"),"-v","error","-y","-i",str(wave_path),"-c:a","aac",str(encoded)],timeout=30)
        asset=probe(encoded)
        self.e.import_entry(asset)
        self.e.timeline["tracks"][0]["muted"]=True
        self.e.add_clips([dict(mediaRef=asset["id"],startFrame=0,endFrame=60)])
        output=self.root/"aac-aligned.mp4"
        render(self.e,self.e.timeline,output)
        def decode(path):
            return array.array("f",run([executable("ffmpeg"),"-v","error","-i",str(path),"-map","0:a:0","-ac","1","-ar","48000","-f","f32le","pipe:1"],timeout=30).stdout)
        a,b=decode(encoded),decode(output)
        n=min(len(a),len(b))
        correlation=sum(a[i]*b[i] for i in range(n))/math.sqrt(sum(v*v for v in a[:n])*sum(v*v for v in b[:n]))
        self.assertGreater(correlation,.98)


if __name__=="__main__":
    unittest.main()
