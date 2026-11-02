# Local separation pilot

This is an experiment, separate from the desktop app. The first run and listening examples are in [the October 27 report](results-2026-10-27/REPORT.md).

`compare.py` uses the existing Cue Atlas matcher through a SQLite read-only adapter. It never writes the source project. `prepare` automatically samples five reviewed cues and three Unknown cues, extracts mono 48 kHz excerpts of at most 20 seconds, and records baseline candidates. `compare` searches matching files in the output's `music` folder using the same project settings.

Run these commands from the Cue Atlas source folder, with a fresh output folder:

```sh
.venv/bin/python experiments/separation_pilot/compare.py prepare /absolute/project.cueatlas /absolute/new-output
.venv/bin/python experiments/separation_pilot/compare.py compare /absolute/project.cueatlas /absolute/new-output
```

Between those commands, run `separate.py` with an isolated AI Python environment, not Cue Atlas's `.venv`:

```sh
/absolute/ai-environment/bin/python experiments/separation_pilot/separate.py /absolute/new-output \
  --source /absolute/Music-Source-Separation-Training \
  --config /absolute/Music-Source-Separation-Training/configs/config_dnr_bandit_v2_mus64.yaml \
  --checkpoint /absolute/checkpoint-multi.ckpt
```

The runner accepts only the verified official BandIt v2 multilingual checkpoint from https://zenodo.org/records/12701995/files/checkpoint-multi.ckpt. Its architecture source, exact package versions, checkpoint SHA-256, and author configuration commit are recorded in the first report's `provenance.json` and `runtime-requirements.txt`. The model and AI runtime are not included in this folder. This trial used Python 3.13, Apple GPU acceleration for the recurrent backbone, and CPU spectral operations. `--device cpu` runs entirely on CPU. Model setup/download and cold startup are not part of the per-excerpt timings.

The temporary setup for this run lives in `/private/tmp/cueatlas-ai-pilot-venv`, `/private/tmp/cueatlas-ai-pilot-models`, and `/private/tmp/cueatlas-ai-pilot-source`. Those directories may be removed by macOS; saved results in this repository remain available.

Reviewed assignments supply provisional expected titles. Unknown candidates remain proposals until checked by listening. A higher evidence count is not a calibrated confidence percentage. This sample does not measure false-positive rates because no dialogue-only negative control was labeled.
