# Palmier Pro — Windows Port (1-to-1 MCP compatible)

Windows reimplementation of [palmier-io/palmier-pro](https://github.com/palmier-io/palmier-pro) (`last-gpl-source`, v0.7.6, GPLv3).

Original is Swift 6.2, SwiftUI + AppKit, AVFoundation, Metal, macOS 26 arm64 only (415 Swift files).
It cannot compile or run on Windows. This port keeps the product contract identical where it matters:

- Same MCP endpoint: `http://127.0.0.1:19789/mcp`
- Same 50 tool names from `ToolDefinitions.swift` (`manage_project`, `get_timeline`, `add_clips`, ...)
- Same timeline math: clips occupy `[start, end)`, end exclusive
- Same project concepts: projects > timelines > tracks (`trackId`) > clips, markers, media library, exports
- Same install strings: `claude mcp add --transport http palmier-pro http://127.0.0.1:19789/mcp`

## Run on Windows

```powershell
npm install
npm start
# UI: http://127.0.0.1:19789/
# MCP: http://127.0.0.1:19789/mcp
```

Requires Node 18+ and `ffmpeg` on PATH (`winget install Gyan.FFmpeg`).

## Mapping (macOS -> Windows)

| macOS original | Windows port |
|---|---|
| AVFoundation decode/encode | FFmpeg |
| Metal / CoreImage preview | HTML canvas + ffmpeg `testsrc`/thumbnails |
| AppKit NSDocument `.palmier` | JSON `data/projects/*.json` |
| Swift MCP SDK server | Node Express JSON-RPC `tools/list`, `tools/call` |
| MLX / speech / generation | stubs (`canGenerate:false`, same receipts) |

## License

GPLv3 (same as upstream source through `last-gpl-source`).
