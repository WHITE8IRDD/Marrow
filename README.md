# Marrow

Free, local pipeline that pulls the marrow out of long videos: the strongest self-contained
moments, rendered as captioned vertical clips for **YouTube Shorts** and **Facebook Reels**.

## How it works

Download → Whisper word timestamps → audio energy → sentence-aligned candidate windows →
heuristic shortlist → local LLM (Ollama) judges hook / standalone / emotion / payoff →
best non-overlapping clips → word-by-word captions (smooth pop + optional karaoke hold)
→ per-shot smart layout with active-speaker focus → 9:16 render.

## Install (Windows PowerShell)

```powershell
winget install ffmpeg                    # then open a NEW terminal
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"                  # add ,diarization for speaker detection
ollama pull llama3.1:8b                  # install Ollama first: https://ollama.com/download
pytest                                   # sanity check; needs no GPU, FFmpeg or Ollama
```

macOS/Linux: same steps with `source venv/bin/activate` and your package manager for FFmpeg.

## Run

```bash
marrow "https://www.youtube.com/watch?v=..." --clips 5 --duration 45 --platform both
marrow "C:\videos\podcast.mp4" --platform shorts --layout blur_fit
marrow "<url>" --no-llm            # skip Ollama, rank by audio and heuristics only
marrow "<url>" --speaker-mode two_up   # auto (default) | two_up | off
marrow-ui                         # web UI at http://localhost:8765
```

The web UI has Home (find-a-video flow), Projects, **Edits** (Premiere-style workspace:
live preview, captions/framing/trim/text inspector, waveform timeline, undo/redo),
and Settings pages.

## Smart layout

Single speakers get a **face-tracked crop**; slides and screen recordings use
**blur fit**. Layouts are chosen per shot and can be overridden in the Edits
inspector. OpenCV is installed with Marrow; the small YuNet face model downloads
itself on first use (or via Settings → Download models now).

### Multi-speaker framing

Home offers three modes (also `--speaker-mode` on the CLI and a radio in the
Streamlit app). The same setting travels through generation, regeneration and the
export dialog:

| Mode | What it does |
|---|---|
| **Auto** (default) | Stacked top/bottom panels only for *verified* two-shots: two different faces that are genuinely on screen at the same time, with captions on the seam. Shot/reverse-shot edits stay solo, so one speaker is never shown twice. |
| **Force two-up** | Always two panels, one per speaker, each **centred on its own subject**. Two detected faces are used when they exist; a speaker the detector missed is anchored on the face the tracker only half-trusted, then on what *moves* in that part of the frame, then on where the picture's detail is. Nothing is ever anchored on a fixed quarter of the frame, and one person is never used for both panels. |
| **Off** | Never stack. Every shot uses the configured fallback framing (center crop / blur fit). |

With three or more people on screen, Auto and Force two-up pick the best *distinct*
pair — preferring faces that are on screen together, then the most persistent, then
the largest, then the left-most — and merge duplicate detections of the same person
(overlapping boxes) instead of repeating a face. Mouth-motion analysis decides who
is talking, so a panel only pushes in on the speaker being heard.

**Speaker centring.** A panel is a head-and-shoulders crop whose centre *is* its
speaker, and **both panels share one width**, so a split reads as one deliberate
composition instead of two differently zoomed shots. The width comes from the
subjects: the crop is narrowed from its intended `4` face-widths only as far as
it takes to put both speakers on their own panel's centre line, floored at `2.2`
face-widths and at `14%` of the frame — a speaker pressed against the source edge
is the one case that is clamped a little off centre instead of shrinking the
panel (and with it, the picture quality) to a stamp. A close pair is narrowed
further so the other speaker stays out of the panel, and two speakers who sit
shoulder to shoulder still get one panel each.

Framing needs two *found* subjects, so a two-up shot that came up short gets a
second look: the frames already sampled for face detection are re-detected with a
lower score threshold and a smaller minimum face. YuNet's own default is `0.9`, so
the strict pass drops exactly the marginal face a two-up panel needs — the head
turned away to listen. If that still leaves one subject, `shots[].views` reports
where the other panel's anchor came from: `subject` (what moves in the part of
the frame no subject occupies — a listener who turned away still moves, then where
the picture's detail is) or `frame` (the frame's own halves, the only case that
cannot be centred: nothing at all was measurable). A blob far smaller than the
speaker found is ignored, so a face on a poster cannot fill a panel.

`scripts/two_up_check.py` reports the number that matters — how far each speaker
sits from the centre of their own panel, in a fraction of the panel's width, with
the face re-detected *inside the crop* those coordinates describe:

```bash
python scripts/two_up_check.py podcast.mp4 --start 12 --end 42       # measure the plan
python scripts/two_up_check.py podcast.mp4 --render --shot-png check.png   # + the encode
```

It exits non-zero when any measured speaker is further than `--tolerance` (5% by
default) off centre. On the fixture two-shots (photographed faces composited into
a 1080p frame, from a mid-frame pair to one speaker at the frame's edge) the worst
measured offset is `0.013` of a panel width; the fixed-width crops it replaced
reached `0.39`, i.e. the panel's own edge. `tests/test_two_up_centering.py` covers
the same ground from the geometry up to a rendered 1080x1920 frame whose halves
are re-detected.

`render.split_screen: true|false` (the older boolean) still works and means
Auto / Off; `render.speaker_mode` wins when both are present. Projects, job
settings and manifests keep both fields, so older clients, scripts and the
Streamlit UI keep working.

**Active-speaker focus.** In stacked shots Marrow watches each face's mouth motion
(gated by the audio energy) to work out who is talking, and gently pushes in on the
active speaker's panel while they speak — the view follows the conversation instead
of sitting still. The focus intervals are stored with each clip (`shots[].active` in
the manifest) and shown as a dot on the shot chips in Edits → Framing.

`python -m marrow <url>` also works.

## Output

```text
output/<video_id>/clip_01_shorts.mp4
output/<video_id>/clip_01_reels.mp4
output/<video_id>/manifest.json      # title, score, reason, hashtags and file paths per clip
```

Downloads, transcripts and LLM scores are cached in `work/<video_id>/`, so re-running with a
different clip count or style is fast. Use `--force` to start over.

## Performance

`scripts/bench.py` measures the work Marrow repeats most (shot analysis, frame
sampling, preview tiles, a forced two-up render) on a synthetic 1080p clip, so
these numbers can be re-checked on your own machine:

```bash
python scripts/bench.py            # everything
python scripts/bench.py sampling   # or: analysis thumbs render probe
```

Measured in a 2-core Linux sandbox (FFmpeg 7.0.2, x264 `veryfast`; synthetic
`testsrc2` source, so treat them as relative, not absolute):

| Step | Before | After | Why |
|---|---|---|---|
| Shot analysis of a 60 s window | 10.6 s on the 1080p source | 1.08 s on the 480p proxy | analysis and face detection run on the preview proxy, and face boxes are scaled back to source pixels |
| Frame sampling, 2.5 fps | 1.82 s (`read()`) | 1.37 s (`grab()` + `retrieve()`) | decoding is unavoidable; converting every skipped frame to BGR is not (1.4× on the proxy too) |
| 5 clip preview tiles | 1.32 s from the 1080p source | 0.24 s from the 480p proxy | tiles are 270×480, so decoding full resolution for them is wasted work (2.9–5.4× across runs) |
| Repeated duration probes | ~60 ms each | ~0 ms | `probe_duration` memoises per (path, size, mtime) |
| Two-up speaker anchoring | — | +0.1 s per 6 s of clip | the motion/detail fallback only runs for shots where the detector did not find both speakers, and it reuses the frames already sampled for face detection |

Rendering is encode-bound, not process-bound: on the same box an 8 s 1080×1920
clip takes ~4.3 s of wall clock, and swapping the scaler from `lanczos` to
`bicubic`/`bilinear` only changes that by ~6–9% while visibly softening the
upscale — so the sharp scaler stayed. The real lever is the encoder
(`render.encoder: h264_nvenc` on an NVIDIA card); the NVENC preset/tune/CQ values
in Settings are applied to both normal renders and exports.


### Device selection and live progress

Transcription and video encoding have separate settings:

| Operation | CPU | NVIDIA GPU |
|---|---|---|
| Speech recognition | Transcription device → CPU | Transcription device → GPU (CUDA) |
| Video rendering / export | Video encoder → CPU (libx264) | Video encoder → NVIDIA GPU (NVENC) |

Explicit encoder choices apply at **every export resolution**, including 1440p.
Auto may fall back to CPU; explicit GPU choices surface failures instead. NVENC is
NVIDIA's dedicated video encoder, not CUDA/3D compute: watch the **NVENC** meter
(or Windows Task Manager → GPU → Video Encode), not just the 3D graph. Scanning,
caption composition and software filters still use CPU, even with NVENC selected.
Cached transcripts need no inference and are labeled **Cached**. Ollama controls
its own CPU/GPU placement; Marrow does not claim GPU use just because it is reachable.

The progress card now separates **Prepare → Transcribe → Rank → Scan → Render → Finish**,
with model loading, scene scanning, speaker tracking and caption generation details.
Render progress includes partial clips and all segments/platforms. FFmpeg jobs
with no media-time advancement for 180 seconds fail with a useful message instead
of waiting forever; other FFmpeg tasks have a 30-minute ceiling. The scan's pause
control pauses **the preview**, including automatic seeking; background processing
continues, as its tooltip states.

Layout sampling stops at the requested clip boundary and bounds retained frame
resolution. Scene-cut detection uses a small video-only stream, and complex filter
threads are bounded to avoid oversubscribing the CPU during parallel GPU encodes.
AI scoring uses batches of four with no per-window retry cascade: failed windows
retain heuristic scores, and a wholly failed batch skips further AI requests.

A forced two-up clip renders in a single pass when every shot is frame-view
stacked (no per-shot segments, no concat step); segment rendering is only used
when the panel geometry actually changes inside a clip.

**Previews stay cheap.** The blur-fit backdrop is a low-resolution canvas mirror
of the foreground video, not a second `<video>`: the preview decodes one stream
per screen instead of two. Previews start at `preload="metadata"` and only start
fetching when they actually play; the Home phone pauses (mirror included) when it
scrolls out of view and resumes when it comes back, clip cards stop decoding the
moment they leave the viewport, and opening the expanded preview parks the Home
copy first — its position and mute state are handed over, and handed back on
close — so exactly one copy is ever playing (or audible).

Checks: `python -m pytest -q` runs the suite (Python tests that need FFmpeg skip
themselves when it is missing). Two UI checks sit above that, and the suite runs
them when their tooling is installed and skips them otherwise:

```bash
npm install jsdom          && node scripts/ui_check.mjs      # Home options + preview media in a DOM
npm install puppeteer-core && node scripts/browser_check.mjs  # clip-card action row in real Chromium
```

`ui_check` loads the real `index.html` + `app.js`, clicks the Home framing control
and asserts the preview media rules (lazy loading, offscreen pause, one playing
copy). `browser_check` lays the real stylesheet out in headless Chromium and
measures the clip-card Download/Edit/More row at five widths — 1280/900/600 px
keep one row with Download primary, 560/390 px put Download on its own row with
Edit + More aligned underneath, and nothing overflows or overlaps at any of them.
With `--shots DIR` it also writes a screenshot per width.

## Tuning

| Goal | Change in `config.yaml` |
|---|---|
| Better picks | Bigger Whisper model, a stronger Ollama model, `llm.max_candidates: 40` |
| Faster | `whisper.model: base`, `llm.model: llama3.2:3b`, `render.encoder: h264_nvenc` |
| Slides or screen recordings | `render.layout: blur_fit` |
| Podcast two-shot panels | Home’s framing control: **Auto** (two-shots only), **Force two-up** (every clip), or **Off** — or `render.speaker_mode` in `config.yaml` (`split_screen: true|false` still works) |
| Split panel too tight/loose | `FACE_FILL` (intended width, in face widths) and `MIN_PANEL_FRACTION` / `PANEL_FACE_FLOOR` (the floor) in `marrow/layout.py`; `NEIGHBOUR_KEEP_OUT` clears a neighbour’s head |
| Captions hidden by app UI | Raise `platforms.<name>.caption_margin_v` |
| Less shouty captions | `captions.uppercase: false` |
| Karaoke-style captions | `captions.preset: karaoke` (spoken words stay highlighted) |
| Opus-Clip-style captions | `captions.preset: opus` (default; smooth color + soft fades) |
| Smoother, more dynamic look | `zoom.enabled: true` (slower; crop layout only) |

Platform limits change. `config.yaml` has YouTube Shorts at 180 s (up to 3 minutes since
October 2024) and Reels at a conservative 90 s. Check each platform's current rules. Most
clips perform best well under the cap, so the default `clip.max_duration` is 60 s.

## Troubleshooting

- **`ffmpeg was not found`**: install FFmpeg and open a new terminal.
- **Nothing looks split-screen**: check the framing mode (Auto keeps shot/reverse-shot footage solo on
  purpose — use Force two-up), and that the YuNet model downloaded (Settings → System check shows
  whether OpenCV and the model are ready; without them only Force two-up can stack, and it falls back
  to motion/detail anchoring, then the frame's own halves).
- **A two-up panel still looks off-centre**: run `python scripts/two_up_check.py <video> --start 12
  --end 42` on the source (add `--shot-png check.png` to see the crops drawn on the frame). A speaker
  more than 5% off centre means the pair was rejected — they sit closer than `SEPARATION` for Auto or
  `SPLIT_SEPARATION` for Force two-up — or only one subject could be placed at all; the printed
  `views` value says which path the shot took.
- **GPU or CUDA/DLL errors**: In **Auto** mode, Marrow retries on CPU when CUDA is unusable
  and shows the reason. Explicit **GPU (CUDA)** mode instead fails with diagnostic details;
  it never silently starts a CPU transcription. CUDA DLL directory handles are kept alive
  on Windows. For GPU speed on NVIDIA cards, install:
  `pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` (cuDNN 9 needs ctranslate2 ≥ 4.5).
  Or set `whisper.device: cpu` to stay on CPU. See faster-whisper's README for details.
- **6 GB VRAM**: Whisper is unloaded before the LLM runs. If Ollama still runs out of memory,
  use a smaller model such as `llama3.2:3b`.
- **Ollama not reachable**: start the Ollama app. Marrow falls back to heuristic ranking and
  logs a warning.
- **"Sign in to confirm you're not a bot", or 403 Forbidden, for a YouTube link**: YouTube wants a
  signed-in session, or a player that can run its JavaScript. Do these in order, then press Retry:
  1. Update the YouTube tools: `pip install -U "yt-dlp[default,deno]"`. The `deno` extra installs the
     JavaScript runtime and `default` installs the solver (`yt-dlp-ejs`). Node.js works too.
     Settings → System check shows what is missing.
  2. (Optional — most videos work without cookies.) Open Settings → YouTube cookies. Sign in to
     YouTube in Firefox or Chromium (or in Chrome or Edge with that browser closed), then pick
     that browser, or choose a cookies.txt file exported while signed in (works with any browser).
     If the saved browser isn't installed, Marrow retries without browser cookies.
  Marrow tries yt-dlp's default client, the `web`/`android` client rotation used in V2/V3, and
  clients that do not need a PO token. YouTube's format availability depends on its current
  auth/token checks, so the format ladder keeps trying fallbacks. If it still fails, try again
  later or from another network.
- **Other yt-dlp download errors**: run `pip install -U "yt-dlp[default,deno]"`. YouTube changes
  often, so keep yt-dlp current.
- **Captions use the wrong font**: install the font on your system and set `captions.font`
  to its exact family name.

## Limitations

- Heuristic and LLM scoring approximate "viral"; they don't replicate Opus Clip's trained model.
- Center-crop framing doesn't track faces or speakers (use `blur_fit` when the subject isn't centered).
- No B-roll or emoji insertion yet.
- Only content you have the rights to repurpose should be processed.
