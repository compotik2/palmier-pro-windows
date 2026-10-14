# Native 0.2.0 — development prerelease

An independent GPLv3 Windows port based on Palmier Pro's last GPL source.
**This release is functional but incomplete, not a feature-complete or
pixel-perfect replacement for the macOS application.**

## Included

- Native Qt 6 window, menus, file dialogs, resizable dark editor panels.
- Media library with real thumbnails, video filmstrip previews and audio
  source waveform images; multitrack timeline with drag/move/edge trim.
- Split/delete/copy/cut/paste, shared undo/redo, properties, gain, opacity,
  speed, basic fades and static text.
- Original core `.palmier` package keys, save/load and preserved unknown fields.
- Shared FFmpeg composition for preview/export, cached Qt playback with audio,
  H.264/H.265, resolution/bitrate, export progress/cancellation and software fallback.
- 18 original-name MCP tool subsets and 2 clearly named Windows extensions;
  official SDK protocol/edit/export verification. Optional BYOK OpenAI chat.
- Portable x64 build, source archive, checksums, licenses, build scripts and CI.

## Validation

34 automated tests pass. Source/native interactions and packaged EXE were
executed on Windows 11 Pro build 26200. Actual decoded video frames and visible
preview pixmaps were checked. REA parsed the final EXE as PE32+ AMD64.
See [VERIFICATION.md](VERIFICATION.md) for commands, hashes and exact scope.

## Requirements and limitations

Extract the entire ZIP and run PalmierProWindows.exe with `_internal` next to
it. FFmpeg/FFprobe 7+ must be installed separately or selected through
FFMPEG_PATH/FFPROBE_PATH. The application is unsigned; no installer is included.

Linked AV/ripple/multicam/nested timelines, keyframes/effects/color/HDR,
speech/caption/model functions, original animation/shortcut/icon parity and
Palmier subscription generation are not ported. Preview first renders a cache;
it is not immediate real-time timeline rendering. Windows 10/manual acceptance
and live API provider use are not certified. Unsupported operations report
errors instead of fabricated success. Consult the README compatibility table.
