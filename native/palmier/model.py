import copy
import json
import math
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path


def uid():
    return str(uuid.uuid4()).upper()


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum or value > 100_000_000:
        raise ValueError(f"{name} must be an integer in [{minimum}, 100000000]")
    return value


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return value


def new_timeline(name="Timeline 1", fps=30, width=1920, height=1080):
    return dict(id=uid(), name=name, fps=fps, width=width, height=height,
                settingsConfigured=True, tracks=[], markers=[])


def new_track(kind, name=None):
    return dict(id=uid(), type=kind, name=name, muted=False, hidden=False,
                syncLocked=True, displayHeight=44, clips=[])


def end(clip):
    return clip["startFrame"] + clip["durationFrames"]


def clip_defaults(kind, ref, start, duration, trim=0):
    return dict(id=uid(), mediaRef=ref, mediaType=kind, sourceClipType=kind,
                startFrame=start, durationFrames=duration, trimStartFrame=trim,
                trimEndFrame=0, speed=1.0, volume=1.0, opacity=1.0,
                fadeInFrames=0, fadeOutFrames=0, fadeInInterpolation="linear",
                fadeOutInterpolation="linear", edgeRounding=0.0, edgeSoftness=0.0,
                transform=dict(centerX=.5, centerY=.5, width=1.0, height=1.0,
                               rotation=0.0, rotationX=0.0, rotationY=0.0,
                               flipHorizontal=False, flipVertical=False),
                crop=dict(left=0.0, top=0.0, right=0.0, bottom=0.0))


def validate_project(doc, manifest):
    if not isinstance(doc, dict) or not doc.get("timelines"):
        raise ValueError("Project must contain at least one timeline")
    ids = set()
    for t in doc["timelines"]:
        integer(t["fps"], "fps", 1)
        if t["fps"] > 120:
            raise ValueError("Frame rates above 120 are not supported")
        for key in ("width", "height"):
            integer(t[key], key, 2)
            if t[key] > 7680 or t[key] % 2:
                raise ValueError("Canvas must have even dimensions up to 7680")
        for entity in [t, *t.get("tracks", []), *[c for tr in t.get("tracks", []) for c in tr["clips"]]]:
            if entity["id"] in ids:
                raise ValueError("Duplicate entity ID")
            ids.add(entity["id"])
        for tr in t.get("tracks", []):
            for c in tr["clips"]:
                integer(c["startFrame"], "startFrame")
                integer(c["durationFrames"], "durationFrames", 1)
                integer(c.get("trimStartFrame", 0), "trimStartFrame")
                integer(c.get("trimEndFrame", 0), "trimEndFrame")
                number(c.get("speed", 1), "speed", .05, 16)
                number(c.get("volume", 1), "volume", 0, 6)
                number(c.get("opacity", 1), "opacity", 0, 1)
    if doc.get("activeTimelineId") not in {t["id"] for t in doc["timelines"]}:
        raise ValueError("activeTimelineId does not identify a timeline")
    if not isinstance(manifest.get("entries"), list):
        raise ValueError("media.json must contain entries")


class Editor:
    """One state owner and one transactional undo path for UI and MCP."""
    def __init__(self):
        self.lock = threading.RLock()
        self.io_lock = threading.Lock()
        self.changed = lambda: None
        self.package = None
        self.name = "Untitled"
        self.doc = {}
        self.manifest = {}
        self.undo_stack = []
        self.redo_stack = []
        self.revision = 0
        self.dirty = False
        self.current_frame = 0
        self.mutation_depth = 0
        self.new()

    @property
    def timeline(self):
        return next(t for t in self.doc["timelines"] if t["id"] == self.doc["activeTimelineId"])

    def snapshot(self):
        with self.lock:
            return copy.deepcopy((self.doc, self.manifest))

    def new(self, name="Untitled", fps=30, width=1920, height=1080):
        with self.lock:
            t = new_timeline(fps=fps, width=width, height=height)
            doc = dict(timelines=[t], activeTimelineId=t["id"], openTimelineIds=[t["id"]])
            manifest = dict(version=2, entries=[], folders=[])
            validate_project(doc, manifest)
            self.doc, self.manifest = doc, manifest
            self.name, self.package = name, None
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.current_frame = 0
            self.dirty = False
            self.revision += 1
        self.changed()

    def mutate(self, label, action):
        with self.lock:
            before = self.snapshot()
            nested = self.mutation_depth > 0
            self.mutation_depth += 1
            try:
                result = action()
                validate_project(self.doc, self.manifest)
            except Exception:
                self.doc, self.manifest = before
                raise
            finally:
                self.mutation_depth -= 1
            if nested:
                return result
            if before != self.snapshot():
                self.undo_stack.append((label, before))
                self.undo_stack = self.undo_stack[-100:]
                self.redo_stack.clear()
                self.dirty = True
                self.revision += 1
            else:
                return result
        self.changed()
        return result

    def undo(self, redo=False):
        with self.lock:
            source, dest = (self.redo_stack, self.undo_stack) if redo else (self.undo_stack, self.redo_stack)
            if not source:
                raise ValueError("Nothing to redo" if redo else "Nothing to undo")
            label, snapshot = source.pop()
            dest.append((label, self.snapshot()))
            self.doc, self.manifest = snapshot
            self.dirty = True
            self.revision += 1
        self.changed()
        return dict(action=label)

    def load(self, package, expected_revision=None):
        with self.io_lock:
            return self._load(package, expected_revision)

    def _load(self, package, expected_revision):
        package = Path(package).resolve()
        doc = json.loads((package / "project.json").read_text(encoding="utf-8-sig"))
        if "timelines" not in doc and "tracks" in doc:
            doc = dict(timelines=[doc], activeTimelineId=doc["id"])
        if not doc.get("activeTimelineId") and doc.get("timelines"):
            doc["activeTimelineId"] = doc["timelines"][0]["id"]
        manifest_file = package / "media.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig")) if manifest_file.exists() else dict(version=2, entries=[], folders=[])
        validate_project(doc, manifest)
        with self.lock:
            if expected_revision is not None and self.revision != expected_revision:
                raise ValueError("Open cancelled: active project changed during file work")
            self.doc, self.manifest = doc, manifest
            self.package, self.name = package, package.stem
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.dirty = False
            self.current_frame = 0
            self.revision += 1
        self.changed()

    def save(self, destination=None):
        with self.io_lock:
            with self.lock:
                old_package = self.package
                doc, manifest = self.snapshot()
                revision = self.revision
                document_id = doc["timelines"][0]["id"]
            target = Path(destination or old_package or "").resolve()
            if not str(target).lower().endswith(".palmier"):
                raise ValueError("Choose a .palmier directory")
            if target.exists() and target != old_package:
                raise ValueError("Save As requires a new package; existing directories are never overwritten")
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=".palmier-", dir=target.parent))
            backup = target.with_name("." + target.name + "." + uid() + ".backup")
            try:
                if target.exists():
                    shutil.copytree(target, stage, dirs_exist_ok=True)
                for entry in manifest["entries"]:
                    if "project" in entry.get("source", {}) and old_package != target:
                        if not old_package:
                            raise ValueError("Project-relative media has no original package")
                        relative = entry["source"]["project"]["relativePath"]
                        source = (old_package / relative).resolve()
                        if not source.is_relative_to(old_package.resolve()):
                            raise ValueError("Media path escapes project package")
                        if source.is_file():
                            relative = entry["source"]["project"]["relativePath"]
                            dest = (stage / relative).resolve()
                            if not dest.is_relative_to(stage.resolve()):
                                raise ValueError("Media path escapes project package")
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, dest)
                (stage / "media").mkdir(exist_ok=True)
                (stage / "project.json").write_text(json.dumps(doc, indent=2, allow_nan=False), encoding="utf-8")
                (stage / "media.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
                with self.lock:
                    if self.doc["timelines"][0]["id"] != document_id:
                        raise ValueError("Save cancelled: active project changed during file work")
                    if target.exists():
                        os.replace(target, backup)
                    try:
                        os.replace(stage, target)
                    except Exception:
                        if backup.exists():
                            os.replace(backup, target)
                        raise
                    self.package, self.name = target, target.stem
                    self.dirty = self.revision != revision
                if backup.exists():
                    shutil.rmtree(backup)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        self.changed()
        return str(target)

    def media_path(self, entry):
        source = entry.get("source", {})
        if "external" in source:
            return Path(source["external"]["absolutePath"])
        if "project" in source and self.package:
            result = (self.package / source["project"]["relativePath"]).resolve()
            if not result.is_relative_to(self.package.resolve()):
                raise ValueError("Media path escapes project package")
            return result
        raise ValueError(f"Cannot resolve media {entry['id']}; relink the source")

    def media(self, ref):
        return next((m for m in self.manifest["entries"] if m["id"] == ref), None)

    def clip(self, clip_id):
        for tr in self.timeline["tracks"]:
            for c in tr["clips"]:
                if c["id"] == clip_id:
                    return tr, c
        raise ValueError("Unknown clip ID: " + clip_id)

    def add_track(self, kind):
        if kind not in ("video", "audio"):
            raise ValueError("Track must be video or audio")
        def action():
            track = new_track(kind)
            self.timeline["tracks"].append(track)
            return track["id"]
        return self.mutate("Add track", action)

    def import_entry(self, entry):
        return self.mutate("Import media", lambda: self.manifest["entries"].append(entry))

    @staticmethod
    def overwrite(track, start, finish, ignore=None):
        output = []
        for c in track["clips"]:
            if c["id"] == ignore or end(c) <= start or c["startFrame"] >= finish:
                output.append(c)
                continue
            original_end = end(c)
            if c["startFrame"] < start:
                left = copy.deepcopy(c)
                left["durationFrames"] = start - c["startFrame"]
                left["fadeOutFrames"] = 0
                output.append(left)
            if original_end > finish:
                right = copy.deepcopy(c)
                right["id"] = uid()
                right["trimStartFrame"] += round((finish - c["startFrame"]) * c.get("speed", 1))
                right["startFrame"], right["durationFrames"] = finish, original_end - finish
                right["fadeInFrames"] = 0
                output.append(right)
        track["clips"] = output

    def add_clips(self, entries):
        if not entries:
            raise ValueError("entries must not be empty")
        def action():
            result = []
            default_tracks = {}
            for e in entries:
                start = integer(e["startFrame"], "startFrame")
                media = self.media(e["mediaRef"])
                if not media:
                    raise ValueError("Unknown mediaRef")
                kind = media["type"]
                if kind not in ("video", "audio", "image"):
                    raise ValueError("Unsupported media type")
                trim = 0
                if "source" in e:
                    if "endFrame" in e or len(e["source"]) != 2:
                        raise ValueError("Use source [startSeconds,endSeconds] OR endFrame")
                    a, b = e["source"]
                    number(a, "source start", 0, media["duration"])
                    number(b, "source end", a, media["duration"])
                    trim, duration = round(a * self.timeline["fps"]), round((b-a) * self.timeline["fps"])
                else:
                    duration = e.get("endFrame", start + round(media["duration"] * self.timeline["fps"])) - start
                integer(duration, "durationFrames", 1)
                if kind != "image" and trim + duration > round(media["duration"] * self.timeline["fps"]):
                    raise ValueError("Clip exceeds available source duration")
                index = e.get("trackIndex")
                if index is None:
                    zone = "audio" if kind == "audio" else "video"
                    if zone not in default_tracks:
                        self.timeline["tracks"].append(new_track(zone))
                        default_tracks[zone] = len(self.timeline["tracks"]) - 1
                    index = default_tracks[zone]
                integer(index, "trackIndex")
                if index >= len(self.timeline["tracks"]):
                    raise ValueError("Unknown trackIndex")
                track = self.timeline["tracks"][index]
                if (track["type"] == "audio") != (kind == "audio"):
                    raise ValueError("Media is incompatible with destination track")
                c = clip_defaults(kind, media["id"], start, duration, trim)
                self.overwrite(track, start, start+duration)
                track["clips"].append(c)
                result.append(c["id"])
            return dict(clipIds=result)
        return self.mutate("Add clips", action)

    def move(self, moves):
        if not moves:
            raise ValueError("moves must not be empty")
        def action():
            targets = []
            for m in moves:
                if "toFrame" not in m and "toTrack" not in m:
                    raise ValueError("Specify toFrame or toTrack")
                tr, c = self.clip(m["clipId"])
                index = m.get("toTrack", self.timeline["tracks"].index(tr))
                integer(index, "toTrack")
                if index >= len(self.timeline["tracks"]):
                    raise ValueError("Unknown track")
                dest = self.timeline["tracks"][index]
                if tr["type"] != dest["type"]:
                    raise ValueError("Cannot move across video/audio zones")
                targets.append((tr, c, dest, integer(m.get("toFrame", c["startFrame"]), "toFrame")))
            for tr, c, dest, frame in targets:
                tr["clips"].remove(c)
                c["startFrame"] = frame
                self.overwrite(dest, frame, end(c))
                dest["clips"].append(c)
            return dict(clipIds=[c["id"] for _, c, _, _ in targets])
        return self.mutate("Move clips", action)

    def split(self, splits):
        def action():
            result = []
            for s in splits:
                tr, c = self.clip(s["clipId"])
                frame = integer(s["atFrame"], "atFrame")
                if not c["startFrame"] < frame < end(c):
                    raise ValueError("Split point must be strictly inside the clip")
                if any(c.get(k) for k in ("positionTrack", "opacityTrack", "volumeTrack", "scaleTrack", "effects")):
                    raise ValueError("Splitting animated/effected original clips is not implemented")
                right = copy.deepcopy(c)
                right["id"] = uid()
                offset = frame - c["startFrame"]
                right["startFrame"], right["durationFrames"] = frame, c["durationFrames"] - offset
                right["trimStartFrame"] += round(offset * c.get("speed", 1))
                right["fadeInFrames"] = 0
                c["durationFrames"], c["fadeOutFrames"] = offset, 0
                tr["clips"].append(right)
                result.append(right["id"])
            return dict(newClipIds=result)
        return self.mutate("Split clips", action)

    def remove(self, clip_ids):
        def action():
            for cid in clip_ids:
                tr, c = self.clip(cid)
                tr["clips"].remove(c)
            return dict(removed=clip_ids)
        return self.mutate("Remove clips", action)

    def properties(self, ids, values):
        allowed = {"durationFrames", "trimStartFrame", "trimEndFrame", "speed", "volumeDb", "opacity", "fadeInFrames", "fadeOutFrames"}
        if not ids or not values or set(values) - allowed:
            raise ValueError("Unsupported or missing clip properties")
        def action():
            for cid in ids:
                _, c = self.clip(cid)
                for k, v in values.items():
                    if k == "volumeDb":
                        c["volume"] = 10 ** (number(v, k, -60, 15) / 20)
                    elif k == "opacity":
                        c[k] = number(v, k, 0, 1)
                    elif k == "speed":
                        number(v, k, .05, 16)
                        if "durationFrames" not in values:
                            c["durationFrames"] = max(1, round(c["durationFrames"] * c.get("speed", 1) / v))
                        c[k] = v
                    else:
                        c[k] = integer(v, k, 1 if k == "durationFrames" else 0)
                if c.get("fadeInFrames", 0) + c.get("fadeOutFrames", 0) > c["durationFrames"]:
                    raise ValueError("Fades exceed clip duration")
                m = self.media(c["mediaRef"])
                if m and m["type"] not in ("image", "text") and c["trimStartFrame"] + round(c["durationFrames"] * c["speed"]) + c.get("trimEndFrame", 0) > round(m["duration"] * self.timeline["fps"]):
                    raise ValueError("Clip exceeds available media; shorten duration with trim")
            return dict(clipIds=ids)
        return self.mutate("Clip properties", action)

    def add_texts(self, entries):
        def action():
            ids = []
            for e in entries:
                if set(e) - {"startFrame", "endFrame", "content", "trackIndex", "style"}:
                    raise ValueError("Text animation/transform is not implemented")
                start = integer(e["startFrame"], "startFrame")
                duration = integer(e["endFrame"]-start, "durationFrames", 1)
                content = e["content"]
                if not isinstance(content, str) or len(content) > 10000:
                    raise ValueError("Text must be a string up to 10000 characters")
                style = e.get("style", {})
                if set(style) - {"fontSize", "color"}:
                    raise ValueError("Only fontSize and color text style are supported")
                size = number(style.get("fontSize", 96), "fontSize", 12, 300)
                color = style.get("color", "#FFFFFF")
                import re
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    raise ValueError("Text color must be #RRGGBB")
                index = e.get("trackIndex")
                if index is None:
                    self.timeline["tracks"].insert(0, new_track("video", "Text"))
                    index = 0
                if type(index) is not int or not 0 <= index < len(self.timeline["tracks"]) or self.timeline["tracks"][index]["type"] == "audio":
                    raise ValueError("Text requires a visual track")
                c = clip_defaults("text", uid(), start, duration)
                c["textContent"], c["textStyle"] = content, dict(fontSize=size, color=color)
                self.overwrite(self.timeline["tracks"][index], start, start+duration)
                self.timeline["tracks"][index]["clips"].append(c)
                ids.append(c["id"])
            return dict(clipIds=ids)
        return self.mutate("Add text", action)
