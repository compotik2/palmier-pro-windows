"""GPLv3 desktop implementation based on Palmier's last GPL source."""
VERSION = "0.3.0"

# Qt's delay-loaded FFmpeg DLLs must be visible outside the process working directory.
import os
if os.name == "nt":
    import ctypes
    from pathlib import Path
    import PySide6
    _root = Path(PySide6.__file__).parent
    _media_dlls = []
    for _name in ("avutil-59.dll", "avcodec-61.dll", "avformat-61.dll", "swresample-5.dll", "swscale-8.dll"):
        _file = _root / _name
        if _file.is_file():
            try:
                _media_dlls.append(ctypes.WinDLL(str(_file)))
            except OSError:
                os.environ.setdefault("QT_MEDIA_BACKEND", "windows")
