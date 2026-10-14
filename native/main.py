import argparse
import json
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from palmier.ui import Window
from palmier.platforms import desktop_name


def main():
    if "--verify-media" in sys.argv:
        from palmier.validation import main as validate
        sys.argv.remove("--verify-media")
        return validate()
    parser=argparse.ArgumentParser()
    parser.add_argument("project",nargs="?")
    parser.add_argument("--mcp-port",type=int,default=19789)
    parser.add_argument("--smoke-test",help="Write startup report and screenshot, then exit")
    args=parser.parse_args()
    app=QApplication(sys.argv)
    app.setApplicationName(desktop_name())
    window=Window(args.mcp_port)
    if args.project:
        window.editor.load(args.project)
    window.show()
    if args.smoke_test:
        window.smoke=True
        def verify():
            report=Path(args.smoke_test).resolve()
            report.parent.mkdir(parents=True,exist_ok=True)
            screenshot=report.with_suffix(".png")
            captured=window.grab().save(str(screenshot))
            report.write_text(json.dumps(dict(windowVisible=window.isVisible(),width=window.width(),height=window.height(),
                mcpPort=window.mcp.port if window.mcp else None,toolCount=len(window.tools.list()),
                screenshot=str(screenshot),captured=captured),indent=2),encoding="utf-8")
            window.close()
            app.exit(0 if captured and window.mcp else 1)
        QTimer.singleShot(1500,verify)
    return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
