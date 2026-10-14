# Native Windows/Linux 0.3.0 — development prerelease

**New: Linux x86_64 portable application and OpenCode connection instructions.**
Independent GPLv3 port of Palmier's last GPL source; still incomplete and not
pixel-perfect. Editing functionality is shared between Windows and Linux.

## Downloads

- `PalmierProLinux-0.3.0-linux-x86_64-portable.tar.gz`: Ubuntu 22.04+ x86_64,
  glibc 2.35+, X11/XWayland; Python and Qt runtime included.
- `PalmierProWindows-0.3.0-win-x64-portable.zip`: Windows x64 portable update.
- Source ZIP, checksums, actual desktop screenshots and verification reports.

FFmpeg/FFprobe 4.4+ with libx264/libx265/drawtext must be installed separately.
Linux also needs the graphics libraries and Liberation/DejaVu fonts listed in
[Linux installation instructions](https://github.com/compotik2/palmier-pro-windows/blob/master/native/LINUX.md).
Extract the complete directory and launch `./PalmierProLinux` or
`PalmierProWindows.exe`; keep `_internal` alongside the executable.

## OpenCode

While the editor is running, merge this server into OpenCode's existing `mcp`
object in `~/.config/opencode/opencode.jsonc`, then restart OpenCode:

```json
"palmier-pro": { "type": "remote", "url": "http://127.0.0.1:19789/mcp", "enabled": true }
```

`opencode mcp list` should report connected. OpenCode uses the user's own AI
provider and controls the active timeline through supported MCP tools.

## Verified

39 tests, official MCP SDK edit/export checks, packaging and execution of the
packaged native editor passed on both Linux and Windows CI. Ubuntu verification
used Xvfb/Openbox and a null audio sink; real mouse/keyboard editing and visible
video playback were checked. This is not certification of all Linux desktops.

[Linux CI](https://github.com/compotik2/palmier-pro-windows/actions/runs/38519481479) ·
[Windows CI](https://github.com/compotik2/palmier-pro-windows/actions/runs/38519481501) ·
[Detailed scope and hashes](https://github.com/compotik2/palmier-pro-windows/blob/master/native/docs/LINUX_VERIFICATION.md).

The original missing features remain: advanced effects/keyframes, linked/ripple/
multicam/nested edits, speech/model functions, Palmier subscription generation
and full original UI/workflow parity. Native Wayland and ARM Linux are not
certified. Preview still renders a composited cache before playback.
