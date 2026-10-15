# Native 0.4.1 — preserve unit-speed audio

Fixes a real soundtrack-fidelity defect found while comparing an exported edit
against its reference. Applying FFmpeg's `atempo=1` was not sample-transparent:
it changed the waveform even though no retiming was requested. Unit-speed clips
now bypass time stretching; actual speed changes retain the tempo chain.

A nonperiodic chirp/music-like regression test reproduced the old failure
(correlation 0.658) and checks the decoded export waveform against its source.
Zero-offset input seeking is also omitted: `-ss 0` discarded AAC encoder
priming and shifted real reference music by roughly 23 ms. A separate AAC
regression verifies waveform alignment. Audio mix legs are normalized to 48 kHz.
56 automated tests, official MCP SDK workflow, native editing/playback and
Windows/Linux packaged execution are the release checks.

Includes all 0.4.0 reliability fixes, portable project saving, `save_project`
MCP extension, canvas presets and export cancellation. It remains a development
prerelease with incomplete original Palmier feature/pixel parity.
