import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from palmier.model import Editor
from palmier.media import ExportQueue,probe,run,executable
from palmier.mcp import Tools,MCPServer

with tempfile.TemporaryDirectory(prefix="palmier-sdk-test-") as directory:
    root=Path(directory)
    media=root/"source.mp4"
    run([executable("ffmpeg"),"-v","error","-y","-f","lavfi","-i","color=red:s=320x180:r=30:d=2","-c:v","libx264","-pix_fmt","yuv420p",str(media)],timeout=30)
    editor=Editor()
    editor.new(width=320,height=180)
    editor.import_entry(probe(media))
    editor.save(root/"test.palmier")
    exports=ExportQueue(editor)
    server=MCPServer(Tools(editor,exports),0)
    print(json.dumps(dict(url=f"http://127.0.0.1:{server.port}/mcp",outputPath=str(root/"export.mp4"))),flush=True)
    try:
        sys.stdin.readline()
        editor.save()
        reopened=Editor()
        reopened.load(root/"test.palmier")
        if (root/"export.mp4").exists():
            info=probe(root/"export.mp4")
            print(json.dumps(dict(export=info,savedClips=sum(len(tr["clips"]) for tr in reopened.timeline["tracks"]))),flush=True)
    finally:
        exports.stop()
        server.stop()
