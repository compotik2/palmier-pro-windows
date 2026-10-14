# Palmier Pro Linux 0.3.0 — native development port

Native Qt 6 Widgets application using the same project model, timeline editor,
FFmpeg render/export pipeline and local MCP server as the Windows build.
This remains an incomplete GPL-source Palmier port, not feature-complete or
pixel-perfect. See README compatibility table and root LICENSE/NOTICE.

## Supported packaging profile

- Linux **x86_64**, built on Ubuntu 22.04 (glibc 2.35).
- Ubuntu 22.04+ is the initial target; other distributions require compatible
  glibc, graphics/audio libraries and media tools. ARM Linux is not packaged.
- X11, or an XWayland session. Native Wayland is not certified.
- FFmpeg/FFprobe **4.4 or newer**, with drawtext, libx264 and libx265.
- Liberation Sans or DejaVu Sans system font. Set `PALMIER_FONT_PATH` to an
  absolute TTF path to use another installed font.

The portable archive includes Python, PySide6/Qt and its shared decoder
libraries. FFmpeg/FFprobe command-line executables remain external.

## Install and launch (Ubuntu)

```bash
sudo apt-get update
sudo apt-get install ffmpeg fonts-liberation fonts-dejavu-core libegl1 libopengl0 libgl1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0
tar -xzf PalmierProLinux-0.3.0-linux-x86_64-portable.tar.gz
cd PalmierProLinux
./PalmierProLinux
```

Extract the entire directory; `_internal` must stay next to the executable.
An optional `.desktop` entry is included. To use it, place the executable on
PATH (for example with a symlink in `~/.local/bin`) and copy the entry into
`~/.local/share/applications`. The tar archive preserves executable permissions.

Editor shortcuts use Ctrl. Projects are directory packages ending `.palmier`.
Linux imports store POSIX absolute paths; project-relative `media/` references
use the same original schema as Windows/macOS. Windows drive-letter paths need
relinking before use on Linux; a relink UI is not implemented.

## Connect OpenCode

Keep Palmier open. Merge this entry into `~/.config/opencode/opencode.jsonc`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "palmier-pro": {
      "type": "remote",
      "url": "http://127.0.0.1:19789/mcp",
      "enabled": true
    }
  }
}
```

Preserve other entries, restart OpenCode and run `opencode mcp list`.
Ask: "Use palmier-pro to inspect the active project and arrange the imported
media into a 20-second timeline." OpenCode uses the user's own configured AI
provider; no OpenAI API key is required by Palmier for external MCP control.
The in-app OpenAI BYOK chat is a separate integration.

Loopback-only HTTP, strict Host validation and browser-Origin rejection apply.
Optional `PALMIER_MCP_TOKEN` requires an Authorization Bearer header configured
in the AI client. Only implemented original tool subsets are advertised.

## Build from source

Install Python 3.11 x64 and venv support plus the runtime dependencies above:

```bash
git clone https://github.com/compotik2/palmier-pro-windows.git
cd palmier-pro-windows/native
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python main.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build.py
./dist/PalmierProLinux/PalmierProLinux --verify-media --output test-output/media.json
```

Output: `dist/PalmierProLinux/PalmierProLinux` and
`dist/PalmierProLinux-0.3.0-linux-x86_64-portable.tar.gz` with SHA256SUMS.
`bash build.sh` runs tests, packaging and the desktop/media check in an existing
graphical session. Node.js 24 is optional for `mcp-client` SDK verification.

GitHub Actions uses Ubuntu 22.04 and Xvfb with a null audio sink to execute the
packaged native window, mouse/keyboard editing, visible video playback and
source/media tests. That verifies automated behavior under a virtual X11
display, not human audio listening, Wayland or all Linux distributions.
