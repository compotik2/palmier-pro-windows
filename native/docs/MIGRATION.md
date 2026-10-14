# Migration baseline and architecture

## Provenance

The official repository was cloned at `c948160b8fc304a3b2a86bf4492329cfedf0230f`.
Its editor source is still the last GPL source at
`8805801fa4df8bc2dbc57cb0a854a1f5108f95c6` (`last-gpl-source`). The previously
cloned local mirror `d9a8b945b85d4ba39ab9244c492bed6e34790f39` has the identical
GPL root tree `a3a51357d50d08034fa5f14799af24da6bf83ecc`.

The GPL source identifies itself as 0.7.6/build 84. Latest upstream v0.11.0
binaries are proprietary and their new implementation source is absent. This
port targets the last GPL editor, not unpublished proprietary functionality.
Source inventory: 415 application Swift files and 198 Swift test files. Static
investigation is not proof of macOS runtime behavior.

## Platform map

| Original | Windows implementation / outstanding work |
|---|---|
| Swift 6.2, SwiftUI, AppKit, NSDocument | Python 3.11 + native Qt 6 Widgets, Windows dialogs, document controller |
| AVFoundation, CoreMedia | FFmpeg frame-based filter graph; Qt Multimedia playback |
| Core Image / Metal compositor | FFmpeg overlay, fps/scale/pad, opacity, fades, audio mixing; advanced effects not ported |
| VideoToolbox | libx264/libx265; optional NVENC attempt with reported software fallback |
| CoreText | FFmpeg drawtext using installed Arial; typography is not identical |
| Network + Swift MCP SDK | Loopback stateless Streamable HTTP JSON-RPC server |
| Security Keychain | Environment-provided credentials, no persisted API keys |
| Speech, CoreML, MLX, Accelerate | Not ported: local speech, diarization, beat/semantic models |
| Sparkle | Manual GitHub release downloads |
| Clerk/Convex proprietary processing | Not included; BYOK OpenAI adapter and external Codex MCP |
| Lottie, color kernels, nested sequences/multicam | Not implemented; unsupported rendering fails explicitly |

Qt was chosen over a web wrapper because the task requires real desktop
widgets, native windows, menus, drag/drop and file dialogs. PySide6 binds the
same C++ Qt 6 widgets; Python owns the application/domain layer. A new C#/C++
render engine would not reuse the Swift-only core and would still need to
replace the Apple media frameworks. This choice delivers a functional native
Windows implementation with a small auditable owner for edits and automation.

## Data flow and invariants

```
Qt mouse / keyboard / inspector     MCP / BYOK tools
              \                      /
                    Editor (RLock)
              transactional mutation + undo
                    /            \
        .palmier package         immutable render snapshot
          project.json               FFmpeg subprocess
          media.json               /                  \
                               preview MP4/PNG      export MP4
                               Qt Multimedia       export job status
```

Clip timing uses `[startFrame, startFrame + durationFrames)` and project FPS.
Source trim is measured in project frames. UI and MCP share domain methods.
Changes are validated then committed as one undo action; failures restore the
exact prior model. Rendering snapshots detach from subsequent edits. Export
jobs serialize rendering; cancellation kills only the owned FFmpeg process.
Output stages to a unique adjacent file and only replaces the destination
after FFmpeg succeeds. Missing media produces an actionable failure.

The project format is a directory named `.palmier`, containing `project.json`
and `media.json`. The Swift associated-value source encoding is retained:
`{"external":{"absolutePath":"C:\\media\\a.mp4"}}` or
`{"project":{"relativePath":"media/a.mp4"}}`. Unknown fields survive save
and load. Unsupported transforms/effects/animation data is retained but export
is refused rather than silently producing a different image.

Save stages and replaces a complete package on the same volume and preserves
unmodified chat/resource files. Save As requires a new package directory.
External assets are references, not collected copies. Apple `/Users/...` paths
need relinking on Windows. Unsupported original fields do not imply working
feature compatibility. Project load/switch/close rejects or asks before losing
unsaved changes.

## Original UI evidence

Source references: `UI/AppTheme.swift`, `UI/TimelineClipColors.swift`,
`Utilities/Constants.swift`, `Editor/EditorView.swift` and
`Help/ShortcutsPane.swift` in the GPL source. Dark background tokens are
`#18191C`, `#1E1F23`, `#26272C`, `#303137`; primary accent `#ECECEC`;
video/audio/image clips `#1D5878`, `#2E7765`, `#715486`.
Native panel order follows agent/library/preview/inspector with lower timeline.
Splitters are resizable, Windows scaling is handled by Qt. Mac system fonts
and SF Symbols are not redistributed; Windows Segoe UI/system chrome differ.

Upstream `assets/palmier-ui.png` is a promotional screenshot with large text
overlays and is not a clean same-size comparison baseline. No macOS runtime is
available here. Pixel-perfect fidelity, matching animations and full shortcut
parity are **not verified and not achieved**. See compatibility table.

## Iterative migration plan

1. Freeze GPL source baseline; map source owners and tool schemas (done).
2. Implement native window, project/package model, shared edits (implemented).
3. Implement a shared FFmpeg render/export path and multitrack timeline (implemented subset).
4. Validate real media, cancellation, persistence, error rollback and MCP (automated tests).
5. Package Windows x64 and execute the resulting EXE (build/smoke test).
6. Future fidelity milestones: linked A/V editing, exact keyframes, ripple,
   nested timelines, multicam, effects/color, immediate streaming preview,
   thumbnail/waveform UI, speech/model replacements and screenshot comparison
   against a running GPL macOS build.

The final milestone is required before this can be called a 1:1 port.
