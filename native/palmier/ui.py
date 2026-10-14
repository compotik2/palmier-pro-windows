import copy
import json
import math
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtCore import Qt, Signal, Slot, QObject, QTimer, QUrl, QRectF, QSize
from PySide6.QtGui import QAction, QKeySequence, QPainter, QColor, QPen, QPixmap, QFont, QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QAbstractScrollArea, QStackedWidget,
    QFileDialog, QMessageBox, QSlider, QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox,
    QDialog, QDialogButtonBox, QLineEdit, QTextEdit, QInputDialog, QProgressBar, QCheckBox, QListView)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QVideoFrame
from .model import Editor, end
from .media import probe, render, duration, frozen_editor, ExportQueue, run, executable
from .mcp import Tools, MCPServer
from .chat import converse
from .platforms import desktop_name, ui_font
from . import VERSION

THEME = """
QWidget {background:#18191C;color:#FAFAFA;font-family:'Segoe UI';font-size:12px;}
QMenuBar,QMenu,QStatusBar {background:#1E1F23;}
QMenu::item:selected {background:#303137;}
QPushButton,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit {background:#26272C;border:1px solid #404148;border-radius:4px;padding:5px;}
QPushButton:hover {background:#303137;} QPushButton:disabled {color:#777;}
QListWidget,QTextEdit {background:#1E1F23;border:1px solid #303137;}
QListWidget::item:selected {background:#303137;}
QSplitter::handle {background:#090A0B;width:1px;height:1px;}
QSlider::groove:horizontal {height:4px;background:#404148;}
QSlider::handle:horizontal {width:10px;margin:-4px 0;background:#ECECEC;border-radius:5px;}
QProgressBar {border:1px solid #404148;text-align:center;} QProgressBar::chunk {background:#2E7765;}
"""
THEME = THEME.replace("Segoe UI", ui_font())
COLORS = dict(video="#1D5878", audio="#2E7765", image="#715486", text="#715486")


class Bridge(QObject):
    changed = Signal()
    completed = Signal(object, object, object)
    playback = Signal(str, int)


class Timeline(QAbstractScrollArea):
    selected = Signal(str)
    seek = Signal(int)
    mediaDropped = Signal(object, int, int)

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.scale = 2.0
        self.selected_id = None
        self.drag = None
        self.ghost = None
        self.setMinimumHeight(170)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())
        self.verticalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    def refresh(self):
        with self.editor.lock:
            self.t = copy.deepcopy(self.editor.timeline)
            self.media_names = {m["id"]:m["name"] for m in self.editor.manifest["entries"]}
            self.frame = self.editor.current_frame
        extent = max(duration(self.t) + self.t["fps"]*5, self.t["fps"]*30)
        self.horizontalScrollBar().setRange(0, max(0, round(extent*self.scale) - self.viewport().width()+160))
        self.verticalScrollBar().setRange(0, max(0, len(self.t["tracks"])*58+28-self.viewport().height()))
        self.viewport().update()

    def position(self, frame):
        return 160 + frame*self.scale - self.horizontalScrollBar().value()

    def frame_at(self, x):
        return max(0, round((x-160+self.horizontalScrollBar().value())/self.scale))

    def row_at(self, y):
        return math.floor((y-28+self.verticalScrollBar().value())/58)

    def paintEvent(self, event):
        if not hasattr(self, "t"):
            return
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), QColor("#18191C"))
        p.setFont(QFont(ui_font(), 9))
        scroll_y = self.verticalScrollBar().value()
        for i, tr in enumerate(self.t["tracks"]):
            y = 28+i*58-scroll_y
            p.fillRect(QRectF(0,y,self.viewport().width(),58), QColor("#1E1F23" if i%2==0 else "#18191C"))
            p.setPen(QColor("#404148"))
            p.drawLine(0,round(y+57),self.viewport().width(),round(y+57))
            for c in tr["clips"]:
                x, w = self.position(c["startFrame"]), c["durationFrames"]*self.scale
                if x+w < 160 or x > self.viewport().width():
                    continue
                p.save()
                p.setClipRect(QRectF(160,28,self.viewport().width()-160,self.viewport().height()-28))
                rect = QRectF(x,y+4,max(2,w),48)
                p.setBrush(QColor(COLORS.get(c["mediaType"], "#715486")))
                p.setPen(QPen(QColor("#ECECEC" if c["id"] == self.selected_id else "#0B0C0E"),2 if c["id"] == self.selected_id else 1))
                p.drawRoundedRect(rect,4,4)
                image=getattr(self,"images",{}).get(c["mediaRef"])
                if image and not image.isNull():
                    p.setClipRect(rect.adjusted(1,20,-1,-1),Qt.IntersectClip)
                    thumb=image.scaled(64,27,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                    if c["mediaType"]=="audio":
                        p.drawPixmap(rect.adjusted(1,20,-1,-1).toRect(),image)
                    else:
                        for pos in range(max(160,round(x)),min(self.viewport().width(),round(x+w)),64):
                            p.drawPixmap(pos,round(y+24),thumb)
                    p.restore()
                    p.save()
                    p.setClipRect(QRectF(160,28,self.viewport().width()-160,self.viewport().height()-28))
                p.setClipRect(rect.adjusted(5,0,-5,0), Qt.IntersectClip)
                p.setPen(QColor("#FAFAFA"))
                label = c.get("textContent") if c["mediaType"] == "text" else self.media_names.get(c["mediaRef"], "Missing media")
                p.drawText(rect.adjusted(7,3,-5,-3), Qt.AlignLeft|Qt.AlignTop, label)
                p.drawText(rect.adjusted(7,21,-5,-3), Qt.AlignLeft|Qt.AlignTop, f"{c['durationFrames']/self.t['fps']:.2f}s")
                p.restore()
            p.fillRect(QRectF(0,y,160,58),QColor("#1E1F23"))
            p.setPen(QColor("#BBBBBF"))
            p.drawText(QRectF(10,y,105,58),Qt.AlignVCenter, tr.get("name") or ("A" if tr["type"]=="audio" else "V")+str(i+1))
            p.drawText(QRectF(119,y,35,58),Qt.AlignCenter,"M" if tr.get("muted") else "♪" if tr["type"]=="audio" else "◉")
        p.fillRect(QRectF(0,0,self.viewport().width(),28),QColor("#26272C"))
        step = max(1, math.ceil(70/self.scale/self.t["fps"])) * self.t["fps"]
        first = self.frame_at(160)//step*step
        p.setPen(QColor("#949499"))
        for f in range(first, self.frame_at(self.viewport().width())+step, step):
            x = self.position(f)
            if x >= 160:
                p.drawLine(round(x),19,round(x),28)
                p.drawText(QRectF(x+3,0,100,25),Qt.AlignVCenter, f"{f/self.t['fps']:.0f}s")
        p.fillRect(QRectF(0,0,160,28),QColor("#26272C"))
        p.drawText(QRectF(10,0,145,28),Qt.AlignVCenter,"Timeline")
        p.setPen(QPen(QColor("#FF524D"),1))
        x = self.position(self.frame)
        if x >= 160:
            p.drawLine(round(x),0,round(x),self.viewport().height())
        if self.ghost:
            start, length, row = self.ghost
            p.setPen(QPen(QColor("#FFFFFF"),1,Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(self.position(start),28+row*58-scroll_y+4,length*self.scale,48))

    def hit(self, pos):
        row = self.row_at(pos.y())
        if pos.x()<160 or not 0 <= row < len(self.t["tracks"]):
            return None
        frame = self.frame_at(pos.x())
        return next(((row,c) for c in reversed(self.t["tracks"][row]["clips"]) if c["startFrame"]<=frame<end(c)),None)

    def mousePressEvent(self, event):
        self.setFocus()
        if event.position().y()<28 and event.position().x()>=160:
            self.seek.emit(self.frame_at(event.position().x()))
            return
        row = self.row_at(event.position().y())
        if event.position().x()<160 and 0<=row<len(self.t["tracks"]):
            tr = self.t["tracks"][row]
            key = "muted" if event.position().x()>115 else "hidden"
            self.window().act(lambda: self.editor.mutate("Track visibility/audio",lambda: self.editor.timeline["tracks"][row].update({key:not tr.get(key)})))
            return
        hit = self.hit(event.position())
        if hit:
            row,c = hit
            self.selected_id = c["id"]
            self.selected.emit(c["id"])
            mode = "left" if abs(event.position().x()-self.position(c["startFrame"]))<7 else "right" if abs(event.position().x()-self.position(end(c)))<7 else "move"
            self.drag = dict(row=row, clip=copy.deepcopy(c), x=event.position().x(), mode=mode)
            self.viewport().update()

    def mouseMoveEvent(self, event):
        if self.drag:
            c=self.drag["clip"]
            delta=round((event.position().x()-self.drag["x"])/self.scale)
            if self.drag["mode"]=="move":
                row=max(0,min(len(self.t["tracks"])-1,self.row_at(event.position().y())))
                self.ghost=(max(0,c["startFrame"]+delta),c["durationFrames"],row)
            elif self.drag["mode"]=="right":
                self.ghost=(c["startFrame"],max(1,c["durationFrames"]+delta),self.drag["row"])
            else:
                start=max(0,min(end(c)-1,c["startFrame"]+delta))
                self.ghost=(start,end(c)-start,self.drag["row"])
            self.viewport().update()

    def mouseReleaseEvent(self, event):
        if self.drag and self.ghost:
            c=self.drag["clip"]
            start,length,row=self.ghost
            mode=self.drag["mode"]
            def edit():
                if mode=="move":
                    self.editor.move([dict(clipId=c["id"],toFrame=start,toTrack=row)])
                elif mode=="right":
                    self.editor.properties([c["id"]],dict(durationFrames=length))
                else:
                    def trim():
                        self.editor.properties([c["id"]],dict(durationFrames=length,trimStartFrame=c.get("trimStartFrame",0)+round((start-c["startFrame"])*c.get("speed",1))))
                        self.editor.move([dict(clipId=c["id"],toFrame=start)])
                    self.editor.mutate("Trim start",trim)
            self.window().act(edit)
        self.drag=self.ghost=None
        self.refresh()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-palmier-media"):
            event.acceptProposedAction()

    def dragMoveEvent(self,event):
        event.acceptProposedAction()

    def dropEvent(self,event):
        row=self.row_at(event.position().y())
        frame=self.frame_at(event.position().x())
        payload = json.loads(bytes(event.mimeData().data("application/x-palmier-media"))) if event.mimeData().hasFormat("application/x-palmier-media") else [u.toLocalFile() for u in event.mimeData().urls()]
        self.mediaDropped.emit(payload,frame,row)
        event.acceptProposedAction()


class MediaList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(96,54))
        self.setGridSize(QSize(112,96))
        self.setResizeMode(QListView.Adjust)
        self.setWordWrap(True)

    def mimeTypes(self):
        return ["application/x-palmier-media"]

    def mimeData(self,items):
        from PySide6.QtCore import QMimeData
        data=QMimeData()
        data.setData("application/x-palmier-media",json.dumps([item.data(Qt.UserRole) for item in items]).encode())
        return data


class Window(QMainWindow):
    def __init__(self, port=19789):
        super().__init__()
        self.editor=Editor()
        self.exports=ExportQueue(self.editor)
        self.tools=Tools(self.editor,self.exports)
        self.bridge=Bridge()
        self.editor.changed=self.bridge.changed.emit
        self.bridge.changed.connect(self.refresh)
        self.bridge.completed.connect(self.finish_task, Qt.QueuedConnection)
        self.bridge.playback.connect(self.control_playback)
        self.tools.playback=self.bridge.playback.emit
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.cache=tempfile.TemporaryDirectory(prefix="palmier-preview-")
        self.preview_cancel=threading.Event()
        self.preview_future=None
        self.preview_revision=-1
        self.preview_job_revision=-1
        self.selected_id=None
        self.images={}
        self.thumbnail_pending=set()
        self.import_busy=False
        self.closing=False
        self.resize(1440,900)
        self.setMinimumSize(1032,600)
        self.setStyleSheet(THEME)
        self.player=QMediaPlayer(self)
        self.audio=QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(1)
        self.player.positionChanged.connect(self.play_position)
        self.player.errorOccurred.connect(lambda error,msg: self.statusBar().showMessage("Playback: "+msg,15000))
        self.build_ui()
        self.build_menu()
        try:
            self.mcp=MCPServer(self.tools,port)
            self.connection.setText(f"MCP · 127.0.0.1:{self.mcp.port}/mcp")
        except OSError as error:
            self.mcp=None
            self.connection.setText("MCP unavailable: "+str(error))
        self.refresh()
        self.poll=QTimer(self)
        self.poll.timeout.connect(self.refresh_exports)
        self.poll.start(300)

    def panel(self,title):
        widget=QWidget()
        layout=QVBoxLayout(widget)
        layout.setContentsMargins(8,6,8,6)
        header=QLabel(title)
        header.setFixedHeight(30)
        layout.addWidget(header)
        return widget,layout

    def build_ui(self):
        outer=QSplitter(Qt.Horizontal)
        agent,al=self.panel("Agent")
        self.chat_log=QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setPlainText("Connect OpenCode via MCP:\n\nAdd a remote MCP server named palmier-pro:\nhttp://127.0.0.1:19789/mcp\n\nRestart OpenCode; ask it to edit the active Palmier project. The editor must stay open.\n\nCodex:\ncodex mcp add palmier-pro --url http://127.0.0.1:19789/mcp\n\nOr set OPENAI_API_KEY for the BYOK assistant below. This build does not reproduce Palmier's subscription generation service.")
        al.addWidget(self.chat_log)
        self.chat_input=QLineEdit()
        self.chat_input.setPlaceholderText("Ask your agent…")
        self.chat_input.returnPressed.connect(self.send_chat)
        al.addWidget(self.chat_input)
        self.model_input=QLineEdit("gpt-4.1-mini")
        al.addWidget(self.model_input)
        self.chat_send=QPushButton("Send · BYOK OpenAI")
        self.chat_send.clicked.connect(self.send_chat)
        al.addWidget(self.chat_send)
        agent.setMinimumWidth(240)
        outer.addWidget(agent)
        work=QSplitter(Qt.Vertical)
        top=QSplitter(Qt.Horizontal)
        media,ml=self.panel("Library")
        import_button=QPushButton("+ Import")
        import_button.clicked.connect(self.import_dialog)
        ml.addWidget(import_button)
        self.search=QLineEdit()
        self.search.setPlaceholderText("Search media")
        self.search.textChanged.connect(self.filter_media)
        ml.addWidget(self.search)
        self.library=MediaList()
        self.library.itemDoubleClicked.connect(lambda item:self.place_media([item.data(Qt.UserRole)],self.editor.current_frame,-1))
        ml.addWidget(self.library)
        media.setMinimumWidth(240)
        top.addWidget(media)
        preview,pl=self.panel("Timeline · Preview")
        self.preview_stack=QStackedWidget()
        self.still=QLabel("Import media, then drag it into the timeline")
        self.still.setAlignment(Qt.AlignCenter)
        self.still.setStyleSheet("background:black;color:#777;")
        self.still.setMinimumSize(300,240)
        self.video=QLabel()
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(300,240)
        self.video.setStyleSheet("background:black;")
        self.sink=QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.present_frame)
        self.preview_stack.addWidget(self.still)
        self.preview_stack.addWidget(self.video)
        pl.addWidget(self.preview_stack,1)
        controls=QHBoxLayout()
        self.timecode=QLabel("00:00:00:00")
        self.timecode.setStyleSheet("color:#F29933;font-family:Consolas;")
        controls.addWidget(self.timecode)
        for label,callback in [("◀",lambda:self.seek(max(0,self.editor.current_frame-1))), ("▶ / Ⅱ",self.toggle_play), ("▶|",lambda:self.seek(self.editor.current_frame+1))]:
            button=QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        pl.addLayout(controls)
        top.addWidget(preview)
        inspector,il=self.panel("Inspector")
        form=QFormLayout()
        self.clip_label=QLabel("Select a clip")
        il.addWidget(self.clip_label)
        self.fields={}
        for key,label in [("startFrame","Start frame"),("durationFrames","Duration frames"),("trimStartFrame","Source trim"),("volumeDb","Volume dB"),("speed","Speed"),("opacity","Opacity"),("fadeInFrames","Fade in frames"),("fadeOutFrames","Fade out frames")]:
            field=QDoubleSpinBox() if key in ("volumeDb","speed","opacity") else QSpinBox()
            low,high = (-60,15) if key=="volumeDb" else (.05,16) if key=="speed" else (0,1) if key=="opacity" else (1,100_000_000) if key=="durationFrames" else (0,100_000_000)
            field.setRange(low,high)
            form.addRow(label,field)
            self.fields[key]=field
        il.addLayout(form)
        apply=QPushButton("Apply properties")
        apply.clicked.connect(self.apply_properties)
        il.addWidget(apply)
        self.text_content=QLineEdit()
        self.text_content.setPlaceholderText("Text clip content")
        il.addWidget(self.text_content)
        update=QPushButton("Update text")
        update.clicked.connect(lambda:self.act(lambda:self.tools.call("update_text",dict(clipIds=[self.selected_id],content=self.text_content.text()))))
        il.addWidget(update)
        il.addStretch()
        inspector.setMinimumWidth(250)
        top.addWidget(inspector)
        top.setSizes([352,600,300])
        work.addWidget(top)
        bottom=QWidget()
        bl=QVBoxLayout(bottom)
        bl.setContentsMargins(0,0,0,0)
        toolbar=QHBoxLayout()
        for text,callback in [("↶",lambda:self.act(self.editor.undo)),("↷",lambda:self.act(lambda:self.editor.undo(True))),
                              ("Split",self.split_selected),("Delete",self.delete_selected),("[",lambda:self.trim_playhead(True)),("]",lambda:self.trim_playhead(False)),
                              ("T",self.add_text),("+ V",lambda:self.act(lambda:self.editor.add_track("video"))),("+ A",lambda:self.act(lambda:self.editor.add_track("audio"))),
                              ("Export",self.export_dialog)]:
            b=QPushButton(text)
            b.clicked.connect(callback)
            toolbar.addWidget(b)
        toolbar.addStretch()
        self.zoom=QSlider(Qt.Horizontal)
        self.zoom.setRange(2,120)
        self.zoom.setValue(20)
        self.zoom.setMaximumWidth(140)
        self.zoom.valueChanged.connect(self.set_zoom)
        toolbar.addWidget(QLabel("Zoom"))
        toolbar.addWidget(self.zoom)
        bl.addLayout(toolbar)
        self.timeline=Timeline(self.editor)
        self.timeline.images=self.images
        self.timeline.selected.connect(self.select_clip)
        self.timeline.seek.connect(self.seek)
        self.timeline.mediaDropped.connect(self.place_media)
        bl.addWidget(self.timeline)
        work.addWidget(bottom)
        work.setSizes([560,300])
        outer.addWidget(work)
        outer.setSizes([240,1200])
        self.setCentralWidget(outer)
        self.connection=QLabel()
        self.statusBar().addPermanentWidget(self.connection)
        self.progress=QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.setAcceptDrops(True)

    def build_menu(self):
        file=self.menuBar().addMenu("File")
        edit=self.menuBar().addMenu("Edit")
        playback=self.menuBar().addMenu("Playback")
        help_menu=self.menuBar().addMenu("Help")
        def action(menu,label,shortcut,callback):
            a=QAction(label,self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(callback)
            menu.addAction(a)
        for label,key,call in [("New project","Ctrl+N",self.new_project),("Open project…","Ctrl+O",self.open_project),("Save","Ctrl+S",self.save_project),("Save As…","Ctrl+Shift+S",lambda:self.save_project(True)),("Import media…","Ctrl+I",self.import_dialog),("Export…","Ctrl+E",self.export_dialog),("Quit","Ctrl+Q",self.close)]:
            action(file,label,key,call)
        for label,key,call in [("Undo","Ctrl+Z",lambda:self.act(self.editor.undo)),("Redo","Ctrl+Shift+Z",lambda:self.act(lambda:self.editor.undo(True))),("Split at playhead","Ctrl+K",self.split_selected),("Delete clip","Delete",self.delete_selected),("Cut clip","Ctrl+X",self.cut_selected),("Copy clip","Ctrl+C",self.copy_selected),("Paste clip","Ctrl+V",self.paste_selected)]:
            action(edit,label,key,call)
        action(playback,"Play / Pause","Space",self.toggle_play)
        action(help_menu,"MCP connection instructions",None,lambda:QMessageBox.information(self,"MCP",self.connection.text()+"\n\nOpenCode: add mcp.palmier-pro with type remote, url http://127.0.0.1:19789/mcp and enabled true in ~/.config/opencode/opencode.jsonc; restart OpenCode.\n\ncodex mcp add palmier-pro --url http://127.0.0.1:19789/mcp\n\nOnly implemented tool subsets are advertised. Loopback only; browser origins refused. Optional PALMIER_MCP_TOKEN requires a Bearer header."))
        action(help_menu,"About / License",None,lambda:QMessageBox.information(self,desktop_name(),f"GPLv3 development port · {VERSION}\nBased on Palmier, Inc. last-gpl-source.\nNative Qt 6 / FFmpeg. Not feature-complete or pixel-perfect.\nSee README, LICENSE and third-party notices."))
        action(help_menu,"About Qt",None,lambda:QMessageBox.aboutQt(self,"Qt licensing"))

    def act(self,callback):
        try:
            return callback()
        except Exception as error:
            QMessageBox.warning(self,"Palmier Pro",str(error))

    def task(self,function,callback):
        future=self.pool.submit(function)
        def done(f):
            try:
                result,error=f.result(),None
            except Exception as ex:
                result,error=None,ex
            if not self.closing:
                self.bridge.completed.emit(callback,result,error)
        future.add_done_callback(done)
        return future

    @Slot(object, object, object)
    def finish_task(self,callback,result,error):
        callback(result,error)

    @Slot()
    def refresh(self):
        if self.closing:
            return
        if self.preview_job_revision != -1 and self.preview_job_revision != self.editor.revision:
            self.preview_cancel.set()
        self.setWindowTitle(self.editor.name+(" *" if self.editor.dirty else "")+" — "+desktop_name())
        self.timeline.refresh()
        with self.editor.lock:
            media=copy.deepcopy(self.editor.manifest["entries"])
        selected=self.library.currentItem().data(Qt.UserRole) if self.library.currentItem() else None
        self.library.clear()
        for m in media:
            try:
                missing=not self.editor.media_path(m).is_file()
            except ValueError:
                missing=True
            item=QListWidgetItem(("⚠ " if missing else "")+m["name"]+f"\n{m['type']} · {m['duration']:.2f}s")
            item.setData(Qt.UserRole,m["id"])
            if m["id"] in self.images:
                item.setIcon(QIcon(self.images[m["id"]]))
            self.library.addItem(item)
            if m["id"]==selected:
                self.library.setCurrentItem(item)
            if not missing and m["id"] not in self.images and m["id"] not in self.thumbnail_pending:
                self.thumbnail_pending.add(m["id"])
                source=self.editor.media_path(m)
                mid=m["id"]
                kind=m["type"]
                target=Path(self.cache.name)/("thumbnail-"+mid+".png")
                def thumbnail(source=source,target=target,kind=kind):
                    args=[executable("ffmpeg"),"-v","error","-y","-i",str(source)]
                    if kind=="audio":
                        args += ["-filter_complex","aformat=channel_layouts=mono,showwavespic=s=512x64:colors=white"]
                    else:
                        args += ["-vf","scale=192:108:force_original_aspect_ratio=decrease,pad=192:108:(ow-iw)/2:(oh-ih)/2"]
                    run(args+["-frames:v","1",str(target)],timeout=60)
                    return target
                def ready(file,error,mid=mid):
                    if not error:
                        if len(self.images)>=256:
                            del self.images[next(iter(self.images))]
                        self.images[mid]=QPixmap(str(file))
                        self.refresh()
                self.task(thumbnail,ready)
        self.filter_media()
        if self.preview_revision!=self.editor.revision and self.player.playbackState()==QMediaPlayer.PlayingState:
            self.player.pause()
            self.statusBar().showMessage("Timeline changed — press Play to rebuild composited playback")
        if self.selected_id:
            try:
                self.select_clip(self.selected_id)
            except ValueError:
                self.selected_id=None
                self.clip_label.setText("Select a clip")

    def filter_media(self):
        for i in range(self.library.count()):
            item=self.library.item(i)
            item.setHidden(self.search.text().lower() not in item.text().lower())

    def select_clip(self,cid):
        self.selected_id=cid
        with self.editor.lock:
            _,c=self.editor.clip(cid)
            self.clip_label.setText(c.get("textContent",c["mediaType"]).split("\n")[0][:40])
            for key,field in self.fields.items():
                value=20*math.log10(max(c.get("volume",1),.001)) if key=="volumeDb" else c.get(key,0)
                field.setValue(value)
            self.text_content.setText(c.get("textContent",""))

    def apply_properties(self):
        if not self.selected_id:
            return
        def edit():
            def action():
                self.editor.properties([self.selected_id],{k:f.value() for k,f in self.fields.items() if k!="startFrame"})
                self.editor.move([dict(clipId=self.selected_id,toFrame=self.fields["startFrame"].value())])
            self.editor.mutate("Inspector edit",action)
        self.act(edit)

    def set_zoom(self,value):
        self.timeline.scale=value/10
        self.timeline.refresh()

    def split_selected(self):
        if self.selected_id:
            self.act(lambda:self.editor.split([dict(clipId=self.selected_id,atFrame=self.editor.current_frame)]))

    def delete_selected(self):
        if self.selected_id:
            self.act(lambda:self.editor.remove([self.selected_id]))

    def copy_selected(self):
        if self.selected_id:
            with self.editor.lock:
                self.clipboard=copy.deepcopy(self.editor.clip(self.selected_id)[1])

    def cut_selected(self):
        self.copy_selected()
        self.delete_selected()

    def paste_selected(self):
        if not getattr(self,"clipboard",None):
            return
        from .model import uid
        def action():
            c=copy.deepcopy(self.clipboard)
            c["id"],c["startFrame"]=uid(),self.editor.current_frame
            track=next((tr for tr in self.editor.timeline["tracks"] if (tr["type"]=="audio")== (c["mediaType"]=="audio")),None)
            if track is None:
                self.editor.add_track("audio" if c["mediaType"]=="audio" else "video")
                track=self.editor.timeline["tracks"][-1]
            self.editor.overwrite(track,c["startFrame"],end(c))
            track["clips"].append(c)
        self.act(lambda:self.editor.mutate("Paste clip",action))

    def trim_playhead(self,left):
        if not self.selected_id:
            return
        def action():
            _,c=self.editor.clip(self.selected_id)
            f=self.editor.current_frame
            if not c["startFrame"]<f<end(c):
                raise ValueError("Playhead must be inside selected clip")
            if left:
                self.editor.properties([c["id"]],dict(durationFrames=end(c)-f,trimStartFrame=c.get("trimStartFrame",0)+round((f-c["startFrame"])*c.get("speed",1))))
                self.editor.move([dict(clipId=c["id"],toFrame=f)])
            else:
                self.editor.properties([c["id"]],dict(durationFrames=f-c["startFrame"]))
        self.act(lambda:self.editor.mutate("Trim to playhead",action))

    def add_text(self):
        text,ok=QInputDialog.getText(self,"Text overlay","Content")
        if ok and text:
            self.act(lambda:self.editor.add_texts([dict(startFrame=self.editor.current_frame,endFrame=self.editor.current_frame+self.editor.timeline["fps"]*5,content=text)]))

    def import_dialog(self):
        files,_=QFileDialog.getOpenFileNames(self,"Import media","","Media (*.mp4 *.mov *.mkv *.mp3 *.wav *.png *.jpg *.jpeg);;All files (*)")
        self.import_paths(files)

    def import_paths(self,files,placement=None):
        if not files:
            return
        revision=self.editor.doc["activeTimelineId"]
        self.statusBar().showMessage("Inspecting media…")
        def work():
            return [probe(file) for file in files]
        def ready(entries,error):
            if error:
                self.act(lambda:(_ for _ in ()).throw(error))
                return
            if revision!=self.editor.doc["activeTimelineId"]:
                self.statusBar().showMessage("Import cancelled: active timeline changed")
                return
            self.editor.mutate("Import media",lambda:self.editor.manifest["entries"].extend(entries))
            self.statusBar().showMessage(f"Imported {len(entries)} media files")
            if placement:
                self.place_media([m["id"] for m in entries],*placement)
        self.task(work,ready)

    def place_media(self,payload,frame,row):
        if any(not self.editor.media(item) for item in payload):
            self.import_paths(payload,(frame,row))
            return
        def place():
            position=frame
            entries=[]
            for ref in payload:
                m=self.editor.media(ref)
                entry=dict(mediaRef=ref,startFrame=position)
                if 0<=row<len(self.editor.timeline["tracks"]):
                    entry["trackIndex"]=row
                entries.append(entry)
                position+=round(m["duration"]*self.editor.timeline["fps"])
            self.editor.add_clips(entries)
        self.act(place)

    def seek(self,frame):
        total=duration(self.editor.timeline)
        self.editor.current_frame=max(0,min(max(0,total-1),frame))
        self.update_timecode()
        self.timeline.refresh()
        if self.preview_revision==self.editor.revision:
            self.preview_stack.setCurrentWidget(self.video)
            self.player.setPosition(round(self.editor.current_frame/self.editor.timeline["fps"]*1000))
            return
        if not total:
            return
        self.preview_cancel.set()
        if self.preview_future:
            self.preview_future.cancel()
        cancel=threading.Event()
        self.preview_cancel=cancel
        revision=self.editor.revision
        self.preview_job_revision=revision
        snapshot=frozen_editor(self.editor)
        destination=Path(self.cache.name)/f"frame-{revision}-{self.editor.current_frame}.png"
        current=self.editor.current_frame
        def work():
            if not destination.exists():
                render(snapshot,snapshot.timeline,destination,cancel=cancel,frame=current)
            return destination
        def ready(file,error):
            if cancel.is_set() or revision!=self.editor.revision:
                return
            if error:
                self.statusBar().showMessage(str(error)[-500:],15000)
                return
            pixmap=QPixmap(str(file))
            self.still.setPixmap(pixmap.scaled(self.still.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
            self.preview_stack.setCurrentWidget(self.still)
        self.preview_future=self.task(work,ready)

    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState:
            self.player.pause()
            return
        if not duration(self.editor.timeline):
            return
        if self.preview_revision==self.editor.revision:
            self.preview_stack.setCurrentWidget(self.video)
            self.player.play()
            return
        self.preview_cancel.set()
        cancel=threading.Event()
        self.preview_cancel=cancel
        snapshot=frozen_editor(self.editor)
        revision=self.editor.revision
        self.preview_job_revision=revision
        destination=Path(self.cache.name)/f"preview-{revision}.mp4"
        self.statusBar().showMessage("Rendering composited playback cache — edits remain available")
        def work():
            if not destination.exists():
                render(snapshot,snapshot.timeline,destination,resolution="720p",bitrate=3,cancel=cancel)
            return destination
        def ready(file,error):
            if cancel.is_set() or revision!=self.editor.revision:
                return
            if error:
                self.act(lambda:(_ for _ in ()).throw(error))
                return
            self.preview_revision=revision
            self.player.setSource(QUrl.fromLocalFile(str(file)))
            self.player.setPosition(round(self.editor.current_frame/self.editor.timeline["fps"]*1000))
            self.preview_stack.setCurrentWidget(self.video)
            self.player.play()
            self.statusBar().showMessage("Composited playback")
        self.task(work,ready)

    @Slot(QVideoFrame)
    def present_frame(self, frame):
        image=frame.toImage()
        if not image.isNull():
            self.video.setPixmap(QPixmap.fromImage(image).scaled(self.video.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))

    @Slot(str, int)
    def control_playback(self,action,frame):
        if action=="seek":
            self.seek(frame)
        elif action=="pause":
            self.player.pause()
            self.preview_cancel.set()
        elif self.player.playbackState()!=QMediaPlayer.PlayingState:
            self.toggle_play()

    def play_position(self,milliseconds):
        self.editor.current_frame=round(milliseconds*self.editor.timeline["fps"]/1000)
        self.timeline.frame=self.editor.current_frame
        self.timeline.viewport().update()
        self.update_timecode()

    def update_timecode(self):
        fps=self.editor.timeline["fps"]
        seconds,frame=divmod(self.editor.current_frame,fps)
        minutes,seconds=divmod(seconds,60)
        hours,minutes=divmod(minutes,60)
        self.timecode.setText(f"{hours:02}:{minutes:02}:{seconds:02}:{frame:02}")

    def export_dialog(self):
        dialog=QDialog(self)
        dialog.setWindowTitle("Export video")
        layout=QVBoxLayout(dialog)
        form=QFormLayout()
        codec=QComboBox()
        codec.addItems(["H.264","H.265"])
        resolution=QComboBox()
        resolution.addItems(["Match Timeline","720p","1080p","2K","4K"])
        bitrate=QDoubleSpinBox()
        bitrate.setRange(.1,200)
        bitrate.setValue(8)
        hardware=QCheckBox("Try NVIDIA NVENC; fall back to software")
        form.addRow("Codec",codec)
        form.addRow("Resolution",resolution)
        form.addRow("Bitrate (Mbps)",bitrate)
        layout.addLayout(form)
        layout.addWidget(hardware)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec():
            file,_=QFileDialog.getSaveFileName(self,"Export",str(Path.home()/"Downloads"/(self.editor.name+".mp4")),"MP4 (*.mp4)")
            if file:
                self.act(lambda:self.exports.start(dict(outputPath=file,codec=codec.currentText(),resolution=resolution.currentText(),bitrateMbps=bitrate.value(),hardware=hardware.isChecked())))

    def refresh_exports(self):
        jobs=self.exports.list()
        active=next((j for j in jobs if j["status"] in ("queued","running")),None)
        if active:
            self.progress.show()
            self.progress.setValue(active["progress"])
            self.progress.setFormat(active["status"]+" %p%")
        elif jobs:
            self.progress.hide()
            latest=jobs[-1]
            if getattr(self,"reported_job",None)!=(latest["jobId"],latest["status"]):
                self.reported_job=(latest["jobId"],latest["status"])
                self.statusBar().showMessage("Export "+latest["status"]+": "+latest.get("error",latest["path"]),20000)

    def confirm_discard(self):
        if not self.editor.dirty:
            return True
        choice=QMessageBox.question(self,"Unsaved project","Discard unsaved changes? Save first using File → Save to keep them.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        return choice==QMessageBox.Yes

    def new_project(self):
        if self.confirm_discard():
            self.player.stop()
            self.preview_cancel.set()
            self.editor.new()

    def open_project(self):
        if not self.confirm_discard():
            return
        file=QFileDialog.getExistingDirectory(self,"Open .palmier package",str(Path.home()))
        if file:
            self.player.stop()
            self.preview_cancel.set()
            revision=self.editor.revision
            self.task(lambda:self.editor.load(file, expected_revision=revision),lambda result,error:self.act(lambda:(_ for _ in ()).throw(error)) if error else self.seek(0))

    def save_project(self,save_as=False):
        target=None
        if save_as or not self.editor.package:
            target,_=QFileDialog.getSaveFileName(self,"Save project",str(Path.home()/(self.editor.name+".palmier")),"Palmier package (*.palmier)")
            if not target:
                return
            if not target.endswith(".palmier"):
                target+=".palmier"
        self.task(lambda:self.editor.save(target),lambda result,error:self.act(lambda:(_ for _ in ()).throw(error)) if error else self.statusBar().showMessage("Saved "+result))

    def send_chat(self):
        prompt=self.chat_input.text().strip()
        if not prompt:
            return
        self.chat_input.clear()
        self.chat_log.append("You: "+prompt)
        self.chat_send.setEnabled(False)
        model=self.model_input.text().strip()
        def ready(result,error):
            self.chat_send.setEnabled(True)
            self.chat_log.append("Agent: "+str(error or result))
        self.task(lambda:converse(prompt,self.tools,model),ready)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self,event):
        self.import_paths([u.toLocalFile() for u in event.mimeData().urls()])
        event.acceptProposedAction()

    def keyPressEvent(self,event):
        if isinstance(self.focusWidget(),(QLineEdit,QTextEdit,QSpinBox,QDoubleSpinBox)):
            super().keyPressEvent(event)
            return
        step=5 if event.modifiers()&Qt.ShiftModifier else 1
        if event.key() in (Qt.Key_Left,Qt.Key_Right):
            self.seek(self.editor.current_frame+step*(-1 if event.key()==Qt.Key_Left else 1))
        elif event.key()==Qt.Key_BracketLeft:
            self.trim_playhead(True)
        elif event.key()==Qt.Key_BracketRight:
            self.trim_playhead(False)
        else:
            super().keyPressEvent(event)

    def closeEvent(self,event):
        if not getattr(self,"smoke",False) and not self.confirm_discard():
            event.ignore()
            return
        self.closing=True
        self.preview_cancel.set()
        self.player.stop()
        self.player.setSource(QUrl())
        self.exports.stop()
        if self.mcp:
            self.mcp.stop()
        self.pool.shutdown(wait=True,cancel_futures=True)
        self.cache.cleanup()
        event.accept()
