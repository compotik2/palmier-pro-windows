import copy
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from .model import uid, end, number
from .platforms import text_font

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def executable(name):
    override = os.environ.get(name.upper() + "_PATH")
    if override:
        return override
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    bundled = base / "vendor" / (name + (".exe" if os.name == "nt" else ""))
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name} not found. Set {name.upper()}_PATH or install FFmpeg.")
    return found


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True,
                          creationflags=CREATE_NO_WINDOW, **kwargs)


def parse_ffmpeg_major(output):
    match = re.search(r"ffmpeg version (?:n)?(\d+)\.(\d+)", output)
    if not match:
        raise ValueError("Cannot identify FFmpeg release version; install FFmpeg 4.4 or newer")
    major = int(match.group(1))
    if major < 4 or (major == 4 and int(match.group(2)) < 4):
        raise ValueError("FFmpeg 4.4 or newer is required")
    return major


@lru_cache(maxsize=8)
def filter_file_option(binary):
    version = run([binary, "-version"], timeout=10).stdout.decode("utf-8", errors="replace")
    return "-/filter_complex" if parse_ffmpeg_major(version) >= 7 else "-filter_complex_script"


def probe(file):
    file = Path(file).resolve()
    if not file.is_file():
        raise ValueError("Media file is missing: " + str(file))
    data = json.loads(run([executable("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(file)], timeout=30).stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = any(s["codec_type"] == "audio" for s in streams)
    image = file.suffix.lower() in (".png", ".jpg", ".jpeg")
    if not video and not audio:
        raise ValueError("No supported video/audio streams")
    duration = 5.0 if image else float(data.get("format", {}).get("duration", video.get("duration", 0) if video else 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Media has no finite positive duration")
    fps = 0.0
    if video:
        a, b = video.get("avg_frame_rate", "0/1").split("/")
        fps = float(a)/float(b) if float(b) else 0
    return dict(id=uid(), name=file.name, type="image" if image else "video" if video else "audio",
                source={"external": {"absolutePath": str(file)}}, duration=duration,
                sourceWidth=video.get("width", 0) if video else 0,
                sourceHeight=video.get("height", 0) if video else 0,
                sourceFPS=fps, hasAudio=audio)


def duration(timeline):
    return max((end(c) for tr in timeline["tracks"] for c in tr["clips"]), default=0)


def assert_renderable(clip):
    for key in ("effects", "opacityTrack", "volumeTrack", "rotationTrack", "positionTrack", "scaleTrack", "cropTrack", "multicamGroupId"):
        if clip.get(key):
            raise ValueError(f"Rendering {key} is not implemented; clip {clip['id']} was not silently flattened")
    if clip.get("blendMode", "normal") not in (None, "normal"):
        raise ValueError("Non-normal blend modes are not implemented")
    tr = clip.get("transform", {})
    defaults = dict(centerX=.5, centerY=.5, width=1., height=1., rotation=0., rotationX=0., rotationY=0., flipHorizontal=False, flipVertical=False)
    if any(tr.get(k, v) != v for k, v in defaults.items()):
        raise ValueError("Non-default transforms are not implemented")
    if any(clip.get("crop", {}).values()) or clip.get("edgeRounding", 0) or clip.get("edgeSoftness", 0):
        raise ValueError("Crop and edge effects are not implemented")
    if clip.get("mediaType") not in ("video", "audio", "image", "text"):
        raise ValueError("Unsupported clip type: " + clip.get("mediaType", "unknown"))
    for key in ("fadeInInterpolation", "fadeOutInterpolation"):
        if clip.get(key, "linear") != "linear":
            raise ValueError("Only linear fade interpolation is currently rendered")


def filter_graph(editor, timeline, work, resolution="Match Timeline"):
    fps = timeline["fps"]
    total = duration(timeline) / fps
    if not total:
        raise ValueError("Cannot render an empty timeline")
    heights = {"720p": 720, "1080p": 1080, "2K": 1440, "4K": 2160}
    if resolution != "Match Timeline" and resolution not in heights:
        raise ValueError("Unsupported export resolution")
    height = heights.get(resolution, timeline["height"])
    width = round(timeline["width"] * height / timeline["height"] / 2) * 2
    args = ["-hide_banner", "-y", "-filter_complex_threads", "1", "-f", "lavfi", "-i",
            f"color=c=black:s={width}x{height}:r={fps}:d={total}", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total}"]
    filters, audios, visual, index, count = [], ["1:a"], "0:v", 2, 0
    for track in reversed(timeline["tracks"]):
        for c in sorted(track["clips"], key=lambda c: c["startFrame"]):
            if track.get("hidden") and c.get("mediaType") != "audio":
                continue
            assert_renderable(c)
            start, length = c["startFrame"] / fps, c["durationFrames"] / fps
            speed, opacity = c.get("speed", 1), c.get("opacity", 1)
            fadein, fadeout = c.get("fadeInFrames", 0) / fps, c.get("fadeOutFrames", 0) / fps
            n = count
            count += 1
            if c["mediaType"] == "text":
                animation = c.get("textAnimation")
                if animation and animation.get("preset", "off") != "off":
                    raise ValueError("Animated text is not implemented")
                if c.get("textFillMode", "color") != "color":
                    raise ValueError("Only color text fill is supported")
                style = c.get("textStyle", {})
                if any(style.get(k) for k in ("bold", "italic", "underline", "strikethrough", "overline", "blur", "tracking", "lineSpacing")):
                    raise ValueError("Advanced text styling is not implemented")
                textfile = work / f"text{n}.txt"
                textfile.write_text(c.get("textContent", ""), encoding="utf-8")
                color = style.get("color", "#FFFFFF")
                if isinstance(color, dict):
                    color = "#" + "".join(f"{round(color.get(k, 1)*255):02x}" for k in ("r", "g", "b"))
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    raise ValueError("Text color must be #RRGGBB")
                font = text_font()
                shutil.copyfile(font, work / "render-font.ttf")
                size = number(style.get("fontSize", 96), "fontSize", 12, 300) * height / timeline["height"]
                alpha = str(opacity)
                if fadein:
                    alpha += f"*min(1\\,(t-{start})/{fadein})"
                if fadeout:
                    alpha += f"*min(1\\,({start+length}-t)/{fadeout})"
                filters.append(f"[{visual}]drawtext=fontfile=render-font.ttf:textfile=text{n}.txt:expansion=none:fontcolor={color}:fontsize={size}:x=(w-text_w)/2:y=(h-text_h)/2:alpha='{alpha}':enable='gte(t,{start})*lt(t,{start+length})'[v{n}]")
                visual = f"v{n}"
                continue
            m = editor.media(c["mediaRef"])
            if not m:
                raise ValueError("Missing media reference: " + c["mediaRef"])
            file = editor.media_path(m)
            if not file.is_file():
                raise ValueError("Missing media: " + str(file))
            if m["type"] == "image":
                args.extend(["-loop", "1"])
            args.extend(["-ss", str(c.get("trimStartFrame", 0)/fps), "-t", str(length*speed), "-i", str(file)])
            source = index
            index += 1
            if c["mediaType"] != "audio":
                vf = f"setpts=(PTS-STARTPTS)/{speed},fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,format=rgba,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1,colorchannelmixer=aa={opacity}"
                if fadein:
                    vf += f",fade=t=in:st=0:d={fadein}:alpha=1"
                if fadeout:
                    vf += f",fade=t=out:st={length-fadeout}:d={fadeout}:alpha=1"
                filters.append(f"[{source}:v]{vf},setpts=PTS+{start}/TB[layer{n}]")
                filters.append(f"[{visual}][layer{n}]overlay=eof_action=pass:repeatlast=0:enable='gte(t,{start})*lt(t,{start+length})'[v{n}]")
                visual = f"v{n}"
            if m.get("hasAudio") and not track.get("muted"):
                remaining, tempo = speed, []
                while remaining > 2:
                    tempo.append("atempo=2")
                    remaining /= 2
                while remaining < .5:
                    tempo.append("atempo=0.5")
                    remaining /= .5
                tempo.append(f"atempo={remaining}")
                af = f"asetpts=PTS-STARTPTS,{','.join(tempo)},atrim=duration={length},volume={c.get('volume',1)}"
                if fadein:
                    af += f",afade=t=in:st=0:d={fadein}"
                if fadeout:
                    af += f",afade=t=out:st={length-fadeout}:d={fadeout}"
                filters.append(f"[{source}:a]{af},adelay={round(start*1000)}:all=1[a{n}]")
                audios.append(f"a{n}")
    filters.append("".join(f"[{a}]" for a in audios) + f"amix=inputs={len(audios)}:duration=longest:normalize=0[aout]")
    return args, filters, visual, total


def render(editor, timeline, destination, codec="H.264", resolution="Match Timeline", bitrate=8,
           hardware=False, cancel=None, progress=lambda p: None, frame=None):
    destination = Path(destination).resolve()
    if destination.suffix.lower() not in (".mp4", ".png"):
        raise ValueError("Use .mp4 export or .png frame destination")
    if codec not in ("H.264", "H.265"):
        raise ValueError("Only H.264 and H.265 are supported")
    number(bitrate, "bitrateMbps", .1, 200)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="palmier-render-") as directory:
        work = Path(directory)
        args, filters, visual, total = filter_graph(editor, timeline, work, resolution)
        script = work / "filters.txt"
        script.write_text(";".join(filters + (["[aout]anullsink"] if frame is not None else [])), encoding="utf-8")
        args.extend([filter_file_option(executable("ffmpeg")), "filters.txt", "-map", visual if visual == "0:v" else f"[{visual}]"])
        if frame is not None:
            args.extend(["-ss", str(frame / timeline["fps"]), "-frames:v", "1", "-threads", "1", "-update", "1"])
        else:
            args.extend(["-map", "[aout]", "-t", str(total)])
        temp = destination.with_name("." + uid() + destination.suffix)
        software = "libx264" if codec == "H.264" else "libx265"
        encoders = ["h264_nvenc" if codec == "H.264" else "hevc_nvenc", software] if hardware and frame is None else [software]
        errors = []
        try:
            for encoder in encoders:
                if cancel and cancel.is_set():
                    raise RuntimeError("Cancelled")
                cmd = [executable("ffmpeg"), *args]
                if frame is None:
                    cmd.extend(["-c:v", encoder, "-b:v", f"{bitrate}M", "-pix_fmt", "yuv420p"])
                    if encoder == software:
                        cmd.extend(["-preset", "fast"])
                    cmd.extend(["-c:a", "aac", "-movflags", "+faststart"])
                else:
                    cmd.extend(["-an"])
                cmd.extend(["-progress", "pipe:1", str(temp)])
                with tempfile.TemporaryFile() as stderr:
                    child = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=stderr, creationflags=CREATE_NO_WINDOW)
                    def watch():
                        while child.poll() is None:
                            if cancel and cancel.wait(.1):
                                child.kill()
                                return
                            if not cancel:
                                threading.Event().wait(.1)
                    watcher = threading.Thread(target=watch, daemon=True)
                    watcher.start()
                    for line in iter(child.stdout.readline, b""):
                        if line.startswith(b"out_time_us="):
                            value = line.strip().split(b"=")[1]
                            if value.isdigit():
                                progress(min(99, int(int(value)/1_000_000/total*100)))
                    code = child.wait()
                    child.stdout.close()
                    watcher.join(1)
                    stderr.seek(0)
                    error = stderr.read().decode("utf-8", errors="replace")[-6000:]
                if cancel and cancel.is_set():
                    raise RuntimeError("Cancelled")
                if code == 0:
                    os.replace(temp, destination)
                    progress(100)
                    return dict(path=str(destination), encoder=encoder, softwareFallback=bool(errors), warnings=errors)
                errors.append(f"{encoder}: {error}")
            raise RuntimeError("\n".join(errors))
        finally:
            temp.unlink(missing_ok=True)


def frozen_editor(editor):
    from .model import Editor
    result = Editor()
    with editor.lock:
        result.doc, result.manifest = editor.snapshot()
        result.package = editor.package
    return result


class ExportQueue:
    def __init__(self, editor):
        self.editor = editor
        self.jobs = {}
        self.lock = threading.RLock()
        self.gate = threading.Semaphore(1)
        self.threads = []

    def start(self, args):
        known = {"mode", "codec", "resolution", "outputPath", "overwrite", "timelineId", "bitrateMbps", "hardware"}
        if set(args) - known or args.get("mode", "video") != "video":
            raise ValueError("Only video export is implemented")
        destination = Path(args.get("outputPath", Path.home() / "Downloads" / (uid() + ".mp4")))
        if not destination.is_absolute() or destination.suffix.lower() != ".mp4":
            raise ValueError("outputPath must be an absolute .mp4 path")
        if destination.exists() and not args.get("overwrite", True):
            raise ValueError("Destination exists")
        snapshot = frozen_editor(self.editor)
        timeline_id = args.get("timelineId", snapshot.doc["activeTimelineId"])
        t = next((t for t in snapshot.doc["timelines"] if t["id"] == timeline_id), None)
        if not t:
            raise ValueError("Unknown timelineId")
        if not duration(t):
            raise ValueError("Cannot export empty timeline")
        job = dict(jobId=uid(), path=str(destination), filename=destination.name, status="queued", progress=0)
        cancel = threading.Event()
        with self.lock:
            if any(j[0]["path"] == str(destination) and j[0]["status"] in ("queued", "running") for j in self.jobs.values()):
                raise ValueError("Destination already has an active export")
            self.jobs[job["jobId"]] = (job, cancel)
        def work():
            with self.gate:
                try:
                    if cancel.is_set():
                        raise RuntimeError("Cancelled")
                    self.patch(job, status="running")
                    if destination.exists() and not args.get("overwrite", True):
                        raise ValueError("Destination exists")
                    result = render(snapshot, t, destination, codec=args.get("codec", "H.264"),
                                    resolution=args.get("resolution", "Match Timeline"), bitrate=args.get("bitrateMbps", 8),
                                    hardware=args.get("hardware", False), cancel=cancel,
                                    progress=lambda p: self.patch(job, progress=p))
                    self.patch(job, status="done", progress=100, **result)
                except Exception as e:
                    self.patch(job, status="cancelled" if cancel.is_set() else "failed", error=str(e))
        worker = threading.Thread(target=work, daemon=True)
        with self.lock:
            self.threads = [thread for thread in self.threads if thread.is_alive()]
            self.threads.append(worker)
        worker.start()
        return copy.deepcopy(job)

    def patch(self, job, **values):
        with self.lock:
            job.update(values)

    def list(self):
        with self.lock:
            return copy.deepcopy([j for j, _ in self.jobs.values()])

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError("Unknown jobId")
            job, event = self.jobs[job_id]
            if job["status"] not in ("queued", "running"):
                raise ValueError("Export is no longer active")
            event.set()

    def stop(self):
        with self.lock:
            for job, event in self.jobs.values():
                event.set()
            threads = list(self.threads)
        for thread in threads:
            thread.join(30)
