# Native Windows/Linux 0.4.0 — editing reliability and portable projects

Development prerelease; original feature/pixel parity remains incomplete.

## Correctness fixes

- Swapping two clips in one move batch no longer removes a pending target.
- Extending duration or changing speed resolves same-track overwrites instead
  of leaving overlapping clips. Conflicting selected destinations fail atomically.
- Split/overwrite/edge-trim keeps surviving fades inside the resulting clip.
- Automatically placed text batches share a single visual track.
- Export cannot replace source media, including existing file aliases.
- `overwrite=false` is enforced atomically when the final output is installed,
  preserving a destination created by another writer while rendering.
- Bulk track removal resolves original indices before deleting any track.
- Inspector start+duration edits and edge trims commit one final geometry,
  preserving unrelated clips at the old position.
- No-op moves preserve history and clip ordering.
- Save As refuses a destination directory that appeared during collection.

## New useful features

- `save_project` MCP desktop extension: save the active project, optionally to
  an absolute `.palmier` path, with `collectMedia: true` for a portable package.
- File → Save portable project copies media into the package and updates live
  and undo/redo media references. Missing media aborts without replacing a save.
- File → Canvas settings: portrait 9:16, landscape 16:9 and square presets.
- Visible Cancel export button; Ctrl+Y redo alongside Ctrl+Shift+Z.

There are now 21 supported tools: 18 original-name subsets and 3 desktop
extensions (`windows_playback`, `windows_redo`, `save_project`). Unsupported
original tools still return explicit errors. Full original compatibility is
not claimed. No proprietary generation service is added.

## Verification

52 automated tests passed locally after reproducing the original failures.
Official MCP SDK edit/readback/undo/export/portable-save checks passed. Native
mouse/keyboard editing and visible video playback were executed locally.
Platform CI builds and packaged execution are recorded in the corresponding
GitHub Actions runs; publication requires passing Linux and Windows checks.
