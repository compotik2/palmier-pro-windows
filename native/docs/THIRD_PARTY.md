# Third-party dependencies and distribution

- **Palmier Pro last-gpl-source**: GPLv3, Palmier, Inc. See root LICENSE/NOTICE.
- **Python 3.11**: PSF license, https://www.python.org/downloads/source/.
- **PySide6 6.8.3 / Qt 6.8.3 / shiboken6 6.8.3**: LGPLv3/GPLv3 and Qt
  third-party licenses. https://download.qt.io/official_releases/qt/6.8/6.8.3/
  and https://download.qt.io/official_releases/QtForPython/pyside6/.
  The onedir package keeps Qt DLLs replaceable. Installed license directories
  are included; consult Qt component licenses for any redistribution changes.
- **PyInstaller 6.16.0**: GPLv2-or-later plus bootloader exception,
  https://github.com/pyinstaller/pyinstaller/tree/v6.16.0.
- **jsonschema 4.25.1**, attrs, referencing, jsonschema-specifications,
  rpds-py: installed Python distribution notices collected during packaging.
- **FFmpeg / FFprobe command-line executables**: bring your own, not redistributed. Tested with Gyan's
  GPLv3-enabled FFmpeg 9.0.2 full build, https://www.gyan.dev/ffmpeg/builds/.
  Source: https://ffmpeg.org/download.html#releases and Gyan's corresponding
  source/build links. Runtime uses FFMPEG_PATH/FFPROBE_PATH or PATH.
  The portable archive records local build version/configuration, not a claim
  that an arbitrary installed binary has identical provenance.
- Qt Multimedia includes separately replaceable LGPL FFmpeg 7 decoder DLLs
  shipped by PySide6 6.8.3. Consult the PySide6/Qt FFmpeg attribution and
  https://code.qt.io/cgit/qt/qtmultimedia.git/tree/src/3rdparty/ffmpeg?h=v6.8.3
  for matching Qt integration/build information and FFmpeg 7 source.
- **Fonts**: Segoe UI in Qt and Arial for drawtext are system-installed fonts.
  They are not packaged or redistributed.

No Apple frameworks, proprietary Palmier binaries, credentials, model weights,
or Palmier subscription backend are distributed with this implementation.
