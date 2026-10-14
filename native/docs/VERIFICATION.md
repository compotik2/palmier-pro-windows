# Native Windows 0.2.0 verification

Executed on **Windows 11 Pro x64, build 26200**, Python 3.11.9,
PySide6/Qt 6.8.3, FFmpeg/FFprobe 9.0.2 full Gyan build.
This report is scoped to the native implementation, not the historical root
Node experiment. Windows 10 and a second Windows 11 machine were not tested.

## Commands and observed results

1. `.venv/Scripts/python.exe -m unittest discover -s tests -v`
   - **34 tests passed**.
   - Transaction rollback, overwrite source offsets, half-open splits, nested
     undo grouping, undo/redo, source bounds/nonfinite rejection, original core
     package round-trip, unknown-field retention, Save As media rebasing,
     package traversal, malformed/stale loads, and edits during background save.
   - Real FFmpeg: MP4/MOV/MKV/MP3/WAV/PNG/JPG, H.264 and H.265, 720p/1080p/4K,
     rendered RGB pixel checks, real text glyph pixels, audio presence/silence,
     fades, gaps, source failures, safe output retention, job completion and
     queued cancellation. Encoder failure is deliberately induced in one test
     so a real subsequent software encode must succeed. This is a controlled
     fallback test, not proof of every GPU vendor.
2. `native/mcp-client`: `npm test`, official MCP TypeScript SDK **1.32.1**.
   - Protocol negotiation and tool discovery succeeded (20 tools).
   - Added/split clips, independently read the timeline, undid and read back.
   - Unsupported original tool produced `isError: true` without mutation.
   - Started real export, polled completion, independently probed the output
     and reopened the saved project to verify persisted clips.
3. `.venv/Scripts/python.exe scripts/verify_desktop.py --output docs/windows-desktop.json`
   - Native visible window; real mouse selection, dragging and edge trim.
   - Ctrl+K split, Ctrl+Z undo and Ctrl+Shift+Z redo.
   - FFmpeg composition then actual Qt video decoding and **visible native
     preview pixmap**, with advancing playback position and attached audio output.
   - Screenshot: [windows-desktop.png](windows-desktop.png).
4. `.venv/Scripts/python.exe scripts/build.py`
   - PyInstaller successfully built x64 onedir EXE and portable ZIP.
5. **Executed the packaged EXE** with `--verify-media --output <temporary-report>`.
   - **Exit code 0**.
   - Mouse select/move/trim, keyboard split/undo/redo, video decoding and
     visible preview all true. 7 decoded frames observed, playback at 166 ms,
     no player error. This automated execution is not a human listening test.
6. **REA `inspect_pe_resources`** against that packaged EXE:
   - Evidence `ev_d8f420195d7faed492c9bb07d4c9dcf6c41c60dc4a38b2c5ee770561061e0da2`.
   - PE32+, machine `34404` (`0x8664`, AMD64).
   - EXE size **2,982,779 bytes**.
   - SHA-256 `4ec1cad3a193359a16cc6ed25a44c079b2b52cd40bd2c3f827f830f6bb0f34de`.
   - Resource inventory complete: 21 entries, 9 resources; manifest and icon
     resource relationships parsed. Static PE inspection does not prove runtime
     behavior; packaged runtime verification is separately recorded above.

Portable ZIP SHA-256:
`2a93db5d3ad44962c486825fbb4f6725ded9cf5ce4eb1a663056df1b2a469176`.
Hashes identify the local released build, not a claim of byte-identical CI output.

## Unverified / incomplete

- Full original 50-tool parity, all workflows, macOS frame-equivalence and
  pixel-perfect UI are not achieved.
- Latest proprietary Palmier implementation is outside the source baseline.
- Human UI acceptance, actual speaker listening, live Codex/OpenAI provider
  use, Windows 10, additional GPU configurations and large-project performance
  remain unverified.
- GitHub Actions results are reported by the workflow run, separately from
  these local results. A workflow file alone is not a successful CI build.
- The compatibility table and manual test plan in the native README enumerate
  missing features. This is a development prerelease, not a completed 1:1 port.
