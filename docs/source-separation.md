# Optional dialogue/music separation: implementation assessment

Status: an isolated BandIt v2 pilot has been run outside the app and its virtual environment. No separation feature is installed or enabled in the desktop app. See [the pilot report](../experiments/separation_pilot/results-2026-10-27/REPORT.md) for results and listening examples.

The useful first integration is **Identify selected cue → Reduce dialogue and retry**. It would process only the selected program interval, keep its timeline origin, and feed the music stem into the existing fingerprint search. Search the original mix as well and show candidates from both, rather than assuming that separation improves every result. Keep results as proposals requiring review; never replace program audio or change cue timing.

Requirements:

- An optional separation backend such as [Audio Separator](https://github.com/nomadkaraoke/python-audio-separator), with a pinned model and verified checkpoint checksum. Its documentation describes PyTorch/ONNX dependencies, automatic model downloads, CPU execution, and Apple Silicon MPS/CoreML acceleration. Model and runtime storage must be measured for the chosen package; there is no single download size for every model.
- A separate supported Python environment, invoked through a subprocess. Cue Atlas currently uses Python 3.14; backend compatibility must be tested independently rather than adding PyTorch/ONNX dependencies to the app's existing environment. The backend documentation explicitly excludes Python 3.14.1.
- One explicit model setup/download step in Settings. After setup, inference can run locally. Keep versioned model files separate from project databases and original media.
- A cancellable background job with progress reporting, a bounded audio-window duration, temporary stem storage, and cleanup on cancellation. Cache results by source checksum, cue interval, model version, and parameters. A matching source file and timestamps are required; reference originals are not required for the fingerprint search.
- Benchmarking on representative dialogue, sound effects, sung music, crossfades, and low-level production mixes. Measure recognition before/after, false matches, wall time, and peak memory on the user's actual Mac. CPU is available, but accelerator support and speed depend on the selected model and hardware.
- A check of each chosen model's redistribution/license terms before bundling it.

Separation is not guaranteed dialogue removal. Many models separate vocals from accompaniment; that can remove a song's singer as well as dialogue, leave effects in the music stem, or distort landmarks enough to hurt recognition. Whether it improves Cue Atlas is an empirical question. Recommend a small pilot using selected difficult cues before adding a permanent app dependency.

Reference playback is independent: fingerprints are sparse landmark hashes and timing data, not encoded audio. They can search an offline library but cannot reconstruct its recordings. Playback stays optional and requires the original recording or a verified reconnect. A future self-contained project could optionally copy preview audio, at the cost of additional storage; this is not required for identification.

## October 27 pilot findings

Five reviewed controls kept their correct first-ranked references after separation, with stronger support. Unknown 073 produced a Get Lost Instrumental candidate after separation at Balanced settings, but Sensitive mode also proposed that title from the original mix with much weaker evidence. This demonstrates stronger matching evidence, not yet an additional verified song beyond Sensitive mode. Unknown assignments require listening review; there were no labeled dialogue-only negative controls.

The isolated runtime plus official checkpoint occupied about 1.6 GB, excluding caches and audio. Warm separation took roughly nine seconds per 20-second excerpt on this Mac using an Apple GPU backbone with CPU spectral operations. These measurements describe this prototype, not a completed installer or full-program workload.
