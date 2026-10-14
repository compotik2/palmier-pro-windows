import copy
import hmac
import json
import math
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from jsonschema import Draft202012Validator
from . import VERSION
from .model import integer, new_timeline, uid, end
from .media import probe, duration

ORIGINAL_TOOLS = "manage_project get_timeline inspect_timeline create_timeline set_active_timeline manage_markers set_project_settings export_project manage_exports get_media inspect_media search_media import_media capture_frame organize_media manage_tracks manage_clip_links add_clips insert_clips move_clips remove_clips split_clips ripple_delete_ranges swap_clip_media set_clip_properties copy_clip_settings set_keyframes apply_layout sync_clips undo manage_multicam change_cam get_multicam get_transcript remove_words remove_silence detect_beats add_texts update_text add_captions apply_color apply_effect inspect_color denoise_audio list_models generate_video generate_image generate_audio upscale_media send_feedback".split()


def obj(properties=None, required=None):
    result = dict(type="object", properties=properties or {}, additionalProperties=False)
    if required:
        result["required"] = required
    return result


def array(schema):
    return dict(type="array", items=schema, minItems=1)


S = dict(type="string")
I = dict(type="integer", minimum=0, maximum=100_000_000)
N = dict(type="number")
B = dict(type="boolean")
STYLE = obj(dict(fontSize=dict(type="number", minimum=12, maximum=300), color=dict(type="string", pattern=r"^#[0-9a-fA-F]{6}$")))
SCHEMAS = {
    "manage_project": obj(dict(action=dict(enum=["list", "open", "create", "close"]), name=S, id=S, path=S, fps=I,
                               aspectRatio=dict(enum=["16:9", "9:16", "1:1", "4:3"]), quality=dict(enum=["720p", "1080p", "2K", "4K"])), ["action"]),
    "get_timeline": obj(dict(startFrame=I, endFrame=I, captionDetail=B)),
    "get_media": obj(dict(ids=array(S), folder=S, pending=B)),
    "import_media": obj(dict(source=obj(dict(path=S), ["path"]), name=S), ["source"]),
    "add_clips": obj(dict(entries=array(obj(dict(mediaRef=S, trackIndex=I, startFrame=I, endFrame=I,
                                                 source=dict(type="array", items=N, minItems=2, maxItems=2)), ["mediaRef", "startFrame"]))), ["entries"]),
    "move_clips": obj(dict(moves=array(obj(dict(clipId=S, toTrack=I, toFrame=I), ["clipId"]))), ["moves"]),
    "remove_clips": obj(dict(clipIds=array(S)), ["clipIds"]),
    "split_clips": obj(dict(splits=array(obj(dict(clipId=S, atFrame=I), ["clipId", "atFrame"]))), ["splits"]),
    "set_clip_properties": obj(dict(clipIds=array(S), durationFrames=I, trimStartFrame=I, trimEndFrame=I,
                                     speed=dict(type="number", minimum=.05, maximum=16),
                                     volumeDb=dict(type="number", minimum=-60, maximum=15),
                                     opacity=dict(type="number", minimum=0, maximum=1), fadeInFrames=I, fadeOutFrames=I), ["clipIds"]),
    "manage_tracks": obj(dict(set=array(obj(dict(trackId=S, index=I, muted=B, hidden=B, syncLocked=B, name=dict(type="string", maxLength=80)))),
                               reorder=array(obj(dict(trackId=S, index=I, to=I), ["to"])),
                               remove=array(dict(oneOf=[I, obj(dict(trackId=S), ["trackId"])])))),
    "add_texts": obj(dict(entries=array(obj(dict(trackIndex=I, startFrame=I, endFrame=I, content=S, style=STYLE), ["startFrame", "endFrame", "content"]))), ["entries"]),
    "update_text": obj(dict(clipIds=array(S), content=S, style=STYLE), ["clipIds"]),
    "undo": obj(),
    "create_timeline": obj(dict(name=S)),
    "set_active_timeline": obj(dict(timelineId=S), ["timelineId"]),
    "set_project_settings": obj(dict(width=I, height=I)),
    "export_project": obj(dict(mode=dict(enum=["video"]), codec=dict(enum=["H.264", "H.265"]),
                               resolution=dict(enum=["Match Timeline", "720p", "1080p", "2K", "4K"]),
                               outputPath=S, overwrite=B, timelineId=S, bitrateMbps=dict(type="number", minimum=.1, maximum=200), hardware=B)),
    "manage_exports": obj(dict(action=dict(enum=["list", "cancel"]), jobId=S), ["action"]),
    "windows_playback": obj(dict(action=dict(enum=["play", "pause", "seek"]), frame=I), ["action"]),
    "windows_redo": obj(),
}


class Tools:
    def __init__(self, editor, exports):
        self.editor = editor
        self.exports = exports
        self.playback = lambda action, frame: (_ for _ in ()).throw(ValueError("No active desktop playback controller"))

    def list(self):
        result = []
        for name, schema in SCHEMAS.items():
            result.append(dict(name=name, description=("Windows extension. " if name.startswith("windows_") else "GPL Palmier tool name; supported Windows subset. ") +
                               f"{name.replace('_',' ')}. Only properties in this schema are implemented; unsupported original modes fail without mutation.", inputSchema=schema))
        return result

    def call(self, name, args):
        if name not in SCHEMAS:
            known = name in ORIGINAL_TOOLS
            raise ValueError(("Unsupported original tool" if known else "Unknown tool") + f": {name}. No changes made.")
        Draft202012Validator(SCHEMAS[name]).validate(args)
        if any(isinstance(v, float) and not math.isfinite(v) for v in args.values()):
            raise ValueError("Nonfinite values are not allowed")
        e = self.editor
        if name == "manage_project":
            return self.project(args)
        if name == "import_media":
            source = Path(args["source"]["path"])
            if not source.is_absolute():
                raise ValueError("source.path must be absolute")
            with e.lock:
                document_id = e.doc["timelines"][0]["id"]
            entry = probe(source)
            entry["name"] = args.get("name", entry["name"])
            with e.lock:
                if e.doc["timelines"][0]["id"] != document_id:
                    raise ValueError("Import cancelled: active project changed")
                e.import_entry(entry)
            return dict(mediaRef=entry["id"], status="ready")
        with e.lock:
            if name == "get_timeline":
                t = copy.deepcopy(e.timeline)
                start, finish = args.get("startFrame", 0), args.get("endFrame", 100_000_000)
                if finish < start:
                    raise ValueError("endFrame precedes startFrame")
                tracks = []
                for index, tr in enumerate(t["tracks"]):
                    clips = []
                    for c in tr["clips"]:
                        if end(c) > start and c["startFrame"] < finish:
                            m = e.media(c["mediaRef"])
                            clips.append(dict(id=c["id"], mediaRef=c["mediaRef"], type=c["mediaType"],
                                              frames=[c["startFrame"], end(c)], name=m["name"] if m else c.get("textContent", "Missing media"),
                                              speed=c.get("speed", 1), opacity=c.get("opacity", 1),
                                              volumeDb=20*math.log10(max(c.get("volume", 1), .001))))
                    tracks.append(dict(trackId=tr["id"], index=index, type=tr["type"], name=tr.get("name"),
                                       muted=tr.get("muted", False), hidden=tr.get("hidden", False), clips=clips))
                return dict(id=t["id"], name=t["name"], fps=t["fps"], width=t["width"], height=t["height"],
                            currentFrame=e.current_frame, canGenerate=False, tracks=tracks, markers=t.get("markers", []))
            if name == "get_media":
                if "folder" in args:
                    raise ValueError("Folder filtering is not yet implemented")
                assets = []
                for m in e.manifest["entries"]:
                    if "ids" in args and m["id"] not in args["ids"]:
                        continue
                    if args.get("pending") and not m.get("generationStatus"):
                        continue
                    item = {k: m[k] for k in ("id", "name", "type", "duration", "sourceWidth", "sourceHeight", "hasAudio") if k in m}
                    try:
                        item["missing"] = not e.media_path(m).is_file()
                    except ValueError:
                        item["missing"] = True
                    assets.append(item)
                return dict(assets=assets, timelines=[dict(id=t["id"], name=t["name"]) for t in e.doc["timelines"]])
            if name == "add_clips":
                return e.add_clips(args["entries"])
            if name == "move_clips":
                return e.move(args["moves"])
            if name == "remove_clips":
                return e.remove(args["clipIds"])
            if name == "split_clips":
                return e.split(args["splits"])
            if name == "set_clip_properties":
                return e.properties(args["clipIds"], {k:v for k,v in args.items() if k != "clipIds"})
            if name == "add_texts":
                return e.add_texts(args["entries"])
            if name == "update_text":
                def action():
                    if not ("content" in args or "style" in args):
                        raise ValueError("No text change supplied")
                    for cid in args["clipIds"]:
                        _, c = e.clip(cid)
                        if c["mediaType"] != "text":
                            raise ValueError("Target is not a text clip")
                        if "content" in args:
                            c["textContent"] = args["content"]
                        if "style" in args:
                            c.setdefault("textStyle", {}).update(args["style"])
                    return dict(clipIds=args["clipIds"])
                return e.mutate("Update text", action)
            if name in ("undo", "windows_redo"):
                return e.undo(name == "windows_redo")
            if name == "manage_tracks":
                def select(selector):
                    if ("trackId" in selector) == ("index" in selector):
                        raise ValueError("Use exactly one trackId or index")
                    if "index" in selector:
                        if selector["index"] >= len(e.timeline["tracks"]):
                            raise ValueError("Unknown track index")
                        return e.timeline["tracks"][selector["index"]]
                    tr = next((tr for tr in e.timeline["tracks"] if tr["id"] == selector["trackId"]), None)
                    if tr is None:
                        raise ValueError("Unknown trackId")
                    return tr
                def action():
                    if not args:
                        raise ValueError("Nothing to do")
                    for item in args.get("reorder", []):
                        tr = select(item)
                        if item["to"] >= len(e.timeline["tracks"]) or e.timeline["tracks"][item["to"]]["type"] != tr["type"]:
                            raise ValueError("Reorder must stay inside its video/audio zone")
                        e.timeline["tracks"].remove(tr)
                        e.timeline["tracks"].insert(item["to"], tr)
                    for item in args.get("set", []):
                        tr = select(item)
                        values = {k:v for k,v in item.items() if k not in ("trackId", "index")}
                        if not values:
                            raise ValueError("No track properties specified")
                        tr.update(values)
                    for item in args.get("remove", []):
                        tr = select(dict(index=item) if type(item) is int else item)
                        e.timeline["tracks"].remove(tr)
                    return dict(status="updated")
                return e.mutate("Manage tracks", action)
            if name == "create_timeline":
                def action():
                    t = new_timeline(args.get("name", "Timeline"), e.timeline["fps"], e.timeline["width"], e.timeline["height"])
                    e.doc["timelines"].append(t)
                    e.doc["activeTimelineId"] = t["id"]
                    return dict(timelineId=t["id"])
                return e.mutate("Create timeline", action)
            if name == "set_active_timeline":
                if args["timelineId"] not in {t["id"] for t in e.doc["timelines"]}:
                    raise ValueError("Unknown timelineId")
                return e.mutate("Activate timeline", lambda: e.doc.update(activeTimelineId=args["timelineId"]))
            if name == "set_project_settings":
                if set(args) != {"width", "height"}:
                    raise ValueError("Supply both width and height; frame-rate rescaling is not implemented")
                return e.mutate("Canvas settings", lambda: e.timeline.update(args))
            if name == "export_project":
                return self.exports.start(args)
            if name == "manage_exports":
                if args["action"] == "list":
                    return dict(exports=self.exports.list())
                self.exports.cancel(args.get("jobId"))
                return dict(status="cancelling", jobId=args["jobId"])
            if name == "windows_playback":
                if args["action"] == "seek" and "frame" not in args:
                    raise ValueError("seek requires frame")
                total = duration(e.timeline)
                if args["action"] != "pause" and not total:
                    raise ValueError("The timeline is empty")
                if args["action"] == "seek" and args["frame"] >= total:
                    raise ValueError("frame must be inside the timeline")
                self.playback(args["action"], args.get("frame", e.current_frame))
                return dict(status="requested")
        raise ValueError("Unsupported operation")

    def project(self, args):
        e, action = self.editor, args["action"]
        with e.lock:
            if action == "list":
                return dict(projects=[dict(id=e.doc["timelines"][0]["id"], name=e.name, path=str(e.package) if e.package else None, active=True)])
            if action == "open" and set(args) != {"action", "path"}:
                raise ValueError("Windows currently opens projects by absolute path only")
            if action == "create" and ("id" in args or "path" in args):
                raise ValueError("create accepts name/fps/aspectRatio/quality")
            if action == "close" and set(args) != {"action"}:
                raise ValueError("Only closing the active desktop project is supported")
            if e.dirty and not e.package:
                raise ValueError("Save the active unsaved project in the desktop before switching projects")
            dirty = e.dirty
        if dirty:
            e.save()
        with e.lock:
            if e.dirty:
                raise ValueError("Project changed during save; save again before switching")
            revision = e.revision
        if action == "open":
            e.load(args["path"], expected_revision=revision)
        else:
            with e.lock:
                if e.revision != revision:
                    raise ValueError("Project changed before switching")
                if action == "create":
                    h = {"720p":720, "1080p":1080, "2K":1440, "4K":2160}[args.get("quality", "1080p")]
                    a, b = [int(x) for x in args.get("aspectRatio", "16:9").split(":")]
                    e.new(args.get("name", "Untitled"), args.get("fps",30), round(h*a/b/2)*2, h)
                else:
                    e.new()
        return dict(id=e.doc["timelines"][0]["id"], name=e.name, status=action)


class MCPServer:
    def __init__(self, tools, port=19789):
        token = os.environ.get("PALMIER_MCP_TOKEN")
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def reply(self, status, value=None):
                data = json.dumps(value, allow_nan=False).encode("utf-8") if value is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.close_connection = True

            def do_GET(self):
                self.reply(405, dict(error="Stateless MCP: use POST /mcp"))

            def do_POST(self):
                self.connection.settimeout(30)
                if self.path != "/mcp":
                    return self.reply(404)
                if self.headers.get("Origin") or self.headers.get("Host") not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                    return self.reply(403, dict(error="Browser origins and non-loopback hosts are refused"))
                if token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                    return self.reply(401)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.reply(415)
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 < length <= 1_048_576:
                        return self.reply(413)
                    request = json.loads(self.rfile.read(length), parse_constant=lambda s: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
                    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                        raise ValueError("Invalid JSON-RPC envelope")
                except Exception:
                    return self.reply(400, dict(jsonrpc="2.0", id=None, error=dict(code=-32700, message="Malformed JSON-RPC request")))
                if "id" not in request:
                    return self.reply(202)
                rid = request["id"]
                method, params = request.get("method"), request.get("params", {})
                if method == "initialize":
                    result = dict(protocolVersion=params.get("protocolVersion", "2025-03-26"),
                                  capabilities=dict(tools=dict(listChanged=False)),
                                  serverInfo=dict(name="palmier-pro-windows", version=VERSION),
                                  instructions="Native Qt editor. Supported GPL tool subsets only. Reads and edits share desktop state. Save unsaved projects before switching.")
                elif method == "ping":
                    result = {}
                elif method == "tools/list":
                    result = dict(tools=tools.list())
                elif method == "tools/call":
                    try:
                        value = tools.call(params["name"], params.get("arguments", {}))
                        result = dict(content=[dict(type="text", text=json.dumps(value, allow_nan=False))], isError=False)
                    except Exception as error:
                        result = dict(content=[dict(type="text", text=str(error))], isError=True)
                else:
                    return self.reply(200, dict(jsonrpc="2.0", id=rid, error=dict(code=-32601, message="Method not found")))
                self.reply(200, dict(jsonrpc="2.0", id=rid, result=result))
        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server.server_port

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
