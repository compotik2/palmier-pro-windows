# Native editor reliability audit — 0.4.1

Verified application commit: `28116321da7599823b54795d048473a97329d50f`.

## Reproduced defects and corrections

- A two-clip swap removed an unprocessed target and raised `list.remove`.
  Batch moves now resolve all targets, remove them first, validate selected
  destination conflicts and then apply overwrite placement atomically.
- Duration extension left overlapping clips on a single track. The shared
  overwrite path now resolves affected neighbors. Inspector and trim operations
  apply final geometry in one transaction instead of overwriting at an old position.
- Split/overwrite could retain a fade longer than its surviving fragment.
  Existing envelopes are fitted to the resulting fragment and invalid explicit
  fade requests remain rejected.
- Automatic text placement created a track per entry. Batches reuse one track.
- Bulk numeric track removal retargeted later indices after the first removal.
  Targets are resolved before deleting any track.
- Export could replace source media and could overwrite a file that appeared
  after an `overwrite=false` check. Source aliases are refused and no-overwrite
  output installation uses an atomic filesystem operation.
- MP3 cover art was treated as the video's primary stream. Attached pictures
  are excluded when classifying imported audio.
- A runner without an audio output could buffer without producing video.
  A missing device is no longer attached; device changes reconfigure playback.
- Applying `atempo=1` changed music despite requesting unit speed. An observed
  chirp correlation of 0.658 reproduced the issue; unit speed now bypasses WSOLA.
- Input `-ss 0` discarded AAC priming in a real reference file, removing about
  23 ms of decoded samples. Zero-offset input seeking is now omitted. AAC and
  nonperiodic audio regression tests compare decoded output waveforms.

## Improvements

- `save_project` MCP extension, including portable media collection.
- Portable Save As, missing-media rollback, source-path preservation across undo,
  and protection against a newly created Save As destination.
- Native canvas presets for portrait, landscape and square projects.
- Visible export cancellation and Ctrl+Y redo.
- CPU-oriented preview decoding default with explicit Qt hardware override.
- Preview future/cancellation diagnostics for packaged verification failures.

## Executed verification

- **56 automated tests passed** locally and in both platform workflows.
- Official MCP SDK 1.32.1 verified discovery, editing/readback, undo, real export,
  portable saving and independent persistence/output checks.
- [Windows CI](https://github.com/compotik2/palmier-pro-windows/actions/runs/38786365479)
  built and executed the packaged application: native editing, activated window,
  decoded frames, visible preview. It explicitly had no audio output device;
  video-only fallback produced frames instead of stalling.
- [Linux CI](https://github.com/compotik2/palmier-pro-windows/actions/runs/38786365552)
  passed on Ubuntu 22.04/Xvfb/Openbox with a null audio sink.
- A real 442-frame project with 33 visual intervals was exported after the
  fixes. All video intervals had decoded motion and photo intervals stayed
  still. Decoded audio correlation with its supplied reference was 0.994985
  after AAC re-encoding, without an alignment offset.

[Release artifacts](https://github.com/compotik2/palmier-pro-windows/releases/tag/native-v0.4.1).

This audit covers the implemented native port. It is not full macOS parity,
exhaustive manual UI acceptance or certification of every driver/distro.
