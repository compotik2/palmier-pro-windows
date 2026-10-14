"""Execute native Qt editing and actual composited video playback."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QPoint,QTimer,QEventLoop
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from palmier.ui import Window
from palmier.media import executable,probe,run
from palmier.platforms import desktop_name


def wait_until(predicate,timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        QApplication.processEvents()
        if predicate():
            return True
        QTest.qWait(25)
    return False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    app=QApplication([])
    app.setApplicationName("Palmier native validation")
    window=Window(0)
    window.smoke=True
    results={}
    with tempfile.TemporaryDirectory(prefix="palmier-desktop-") as temp:
        file=Path(temp)/"sample.mp4"
        run([executable("ffmpeg"),"-v","error","-y","-f","lavfi","-i","testsrc2=s=320x180:r=30:d=3",
             "-f","lavfi","-i","sine=frequency=440:duration=3","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(file)],timeout=30)
        window.editor.new(fps=30,width=320,height=180)
        entry=probe(file)
        window.editor.import_entry(entry)
        window.editor.add_track("video")
        cid=window.editor.add_clips([dict(mediaRef=entry["id"],trackIndex=0,startFrame=0,endFrame=90)])["clipIds"][0]
        window.show()
        window.raise_()
        window.activateWindow()
        results["windowActivated"]=wait_until(window.isActiveWindow,timeout=5)
        QTest.qWait(300)
        point=QPoint(round(window.timeline.position(15)),52)
        QTest.mouseClick(window.timeline.viewport(),Qt.LeftButton,pos=point)
        results["mouseSelectClip"]=window.selected_id==cid
        QTest.mousePress(window.timeline.viewport(),Qt.LeftButton,pos=point)
        moved=QPoint(point.x()+60,point.y())
        QTest.mouseMove(window.timeline.viewport(),moved)
        QTest.mouseRelease(window.timeline.viewport(),Qt.LeftButton,pos=moved)
        results["mouseMoveClip"]=window.editor.clip(cid)[1]["startFrame"]==30
        window.editor.undo()
        edge=QPoint(round(window.timeline.position(90))-3,52)
        QTest.mousePress(window.timeline.viewport(),Qt.LeftButton,pos=edge)
        trimmed=QPoint(edge.x()-60,edge.y())
        QTest.mouseMove(window.timeline.viewport(),trimmed)
        QTest.mouseRelease(window.timeline.viewport(),Qt.LeftButton,pos=trimmed)
        results["mouseTrimClip"]=window.editor.clip(cid)[1]["durationFrames"]==60
        window.editor.undo()
        window.editor.current_frame=30
        QTest.keyClick(window,Qt.Key_K,Qt.ControlModifier)
        results["keyboardSplit"]=len(window.editor.timeline["tracks"][0]["clips"])==2
        QTest.keyClick(window,Qt.Key_Z,Qt.ControlModifier)
        results["keyboardUndo"]=len(window.editor.timeline["tracks"][0]["clips"])==1
        QTest.keyClick(window,Qt.Key_Z,Qt.ControlModifier|Qt.ShiftModifier)
        results["keyboardRedo"]=len(window.editor.timeline["tracks"][0]["clips"])==2
        window.editor.add_texts([dict(startFrame=0,endFrame=90,content=desktop_name(),style=dict(fontSize=24,color="#FFFFFF"))])
        frames=[]
        window.sink.videoFrameChanged.connect(lambda frame:frames.append(frame.isValid()))
        window.editor.current_frame=0
        window.toggle_play()
        results["renderedPlaybackFrames"]=wait_until(lambda:len(frames)>2 and window.player.position()>150 and window.video.pixmap() is not None and not window.video.pixmap().isNull())
        results["previewPixmapVisible"]=window.video.pixmap() is not None and not window.video.pixmap().isNull()
        results["decodedVideoFrameCount"]=len(frames)
        results["playbackPositionMs"]=window.player.position()
        results["playerError"]=window.player.errorString()
        results["playerAvailable"]=window.player.isAvailable()
        results["mediaStatus"]=str(window.player.mediaStatus())
        results["playbackState"]=str(window.player.playbackState())
        results["source"]=window.player.source().toString()
        results["statusMessage"]=window.statusBar().currentMessage()
        results["audioOutputConnected"]=window.player.audioOutput() is window.audio
        window.player.pause()
        target=Path(args.output).resolve()
        target.parent.mkdir(parents=True,exist_ok=True)
        results["screenshot"]=str(target.with_suffix(".png"))
        results["screenshotCaptured"]=window.grab().save(results["screenshot"])
        results["windowVisible"]=window.isVisible()
        results["mcpPort"]=window.mcp.port if window.mcp else None
        results["manualVisualReview"]="not performed; automated interaction/playback only"
        target.write_text(json.dumps(results,indent=2),encoding="utf-8")
        print(json.dumps(results,indent=2))
        window.close()
        required=["windowActivated","mouseSelectClip","mouseMoveClip","mouseTrimClip","keyboardSplit","keyboardUndo","keyboardRedo","renderedPlaybackFrames","previewPixmapVisible","screenshotCaptured","windowVisible"]
        return 0 if all(results[k] for k in required) else 1


if __name__=="__main__":
    raise SystemExit(main())
