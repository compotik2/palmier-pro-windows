# Linux 0.3.0 and OpenCode verification

Verified application source commit:
`1fb720a0ba82e3be23470b50aebd3f26b8701547`.

## Linux execution

[Successful Ubuntu build and execution](https://github.com/compotik2/palmier-pro-windows/actions/runs/38519481479).

- Ubuntu 22.04 x86_64, Python 3.11, PySide6/Qt 6.8.3.
- System FFmpeg 4.4: legacy filter-file CLI path and Linux font resolution.
- **39 unit/integration tests passed**, including real media exports,
  failure rollback, cancellation, persistence and platform handling.
- Official MCP SDK 1.32.1: discovery, timeline mutation/readback, undo,
  real export completion, independent output probe and persisted-project readback.
- Packaged **ELF executable actually launched** under Xvfb/Openbox.
- Native window activated; mouse select/move/trim; keyboard split/undo/redo.
- Qt software decode and visible preview pixmap, 28 decoded video frames,
  playback at 1200 ms, no player error.
- Attached audio output used a CI null sink. This is not a human listening test.

Portable tar.gz SHA-256:
`d8e6927e8e3f07212510b3b76c6c38b3f71a462ab2e672c56bd2d3e5ed5a6ff2`.

The downloaded archive checksum and x86_64 ELF header/execute permissions are
verified by `scripts/prepare_release.py` before release publication.

## Windows regression check

[Successful Windows build and execution](https://github.com/compotik2/palmier-pro-windows/actions/runs/38519481501).

The same source passed 39 tests, MCP SDK checks, packaging and packaged native
editing/playback checks. Window activation, mouse operations, shortcuts and
visible preview all passed; 7 decoded frames, playback at 192 ms, no player error.

Portable ZIP SHA-256:
`aab72338bdd433cdaa12df2161618f598fe2b53a95269c07407ede5546431061`.

## OpenCode connection

On the user's Windows installation, OpenCode 1.19.0 reported both `rea` and
`palmier-pro` **connected** after adding the remote server entry to
`~/.config/opencode/opencode.jsonc`. The previous configuration was backed up
as `opencode.jsonc.palmier.backup` and unrelated entries were preserved.

The running conversation still needs an OpenCode restart to load newly added
MCP tools. Palmier must stay open. This connection enables external OpenCode
control using the user's configured AI provider; it does not redirect Palmier's
in-app OpenAI chat to OpenCode.

## Boundaries

Linux initial target: Ubuntu 22.04+ x86_64, glibc 2.35+, X11/XWayland.
Native Wayland, ARM, other distribution certifications, physical GPU/audio
acceptance and full macOS feature/pixel parity remain unverified or incomplete.
No Linux application was executed on the local Windows host; execution evidence
comes from the named Ubuntu runner, and the released tar.gz is that CI artifact.
