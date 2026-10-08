# Marrow

Free, local pipeline that pulls the marrow out of long videos: the strongest self-contained
moments, rendered as captioned vertical clips for **YouTube Shorts** and **Facebook Reels**.

## How it works

Download → Whisper word timestamps → audio energy → sentence-aligned candidate windows →
heuristic shortlist → local LLM (Ollama) judges hook / standalone / emotion / payoff →
best non-overlapping clips → word-by-word captions → 9:16 render.

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
marrow-ui                         # web UI at http://localhost:8765
```

The web UI has Home (find-a-video flow), Projects, **Edits** (Premiere-style workspace:
live preview, captions/framing/trim/text inspector, waveform timeline, undo/redo),
and Settings pages.

## Smart layout

Clips with two people on camera render **stacked** (top/bottom panels with captions
on the seam); single speakers get a **face-tracked crop**; slides and screen
recordings use **blur fit**. Fully automatic per shot — override per shot in the
Edits inspector or Framing control. Face detection is optional:
`pip install -e ".[vision]"` (OpenCV YuNet, local model, ~230 KB auto-download).
Without it, Marrow uses the configured crop/blur fit and logs one warning.

`python -m marrow <url>` also works.

## Output

```text
output/<video_id>/clip_01_shorts.mp4
output/<video_id>/clip_01_reels.mp4
output/<video_id>/manifest.json      # title, score, reason, hashtags and file paths per clip
```

Downloads, transcripts and LLM scores are cached in `work/<video_id>/`, so re-running with a
different clip count or style is fast. Use `--force` to start over.

## Tuning

| Goal | Change in `config.yaml` |
|---|---|
| Better picks | Bigger Whisper model, a stronger Ollama model, `llm.max_candidates: 40` |
| Faster | `whisper.model: base`, `llm.model: llama3.2:3b`, `render.encoder: h264_nvenc` |
| Slides or screen recordings | `render.layout: blur_fit` |
| Captions hidden by app UI | Raise `platforms.<name>.caption_margin_v` |
| Less shouty captions | `captions.uppercase: false` |
| Smoother, more dynamic look | `zoom.enabled: true` (slower; crop layout only) |

Platform limits change. `config.yaml` has YouTube Shorts at 180 s (up to 3 minutes since
October 2024) and Reels at a conservative 90 s. Check each platform's current rules. Most
clips perform best well under the cap, so the default `clip.max_duration` is 60 s.

## Troubleshooting

- **`ffmpeg was not found`**: install FFmpeg and open a new terminal.
- **GPU or CUDA/DLL errors**: Marrow exposes pip-installed CUDA libraries automatically and retries
  on CPU when the GPU is unusable (the UI shows the reason). For GPU speed on NVIDIA cards, install:
  `pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` (cuDNN 9 needs ctranslate2 ≥ 4.5).
  Or set `whisper.device: cpu` to stay on CPU. See faster-whisper's README for details.
- **6 GB VRAM**: Whisper is unloaded before the LLM runs. If Ollama still runs out of memory,
  use a smaller model such as `llama3.2:3b`.
- **Ollama not reachable**: start the Ollama app. Marrow falls back to heuristic ranking and
  logs a warning.
- **Find video says 403 or "not a bot"**: open Settings → YouTube cookies and pick your browser (or a cookies.txt file). The preview uses the same cookies as the download now, and when the preview itself fails you can still press "Try generating anyway".
- **yt-dlp download errors**: run `pip install -U yt-dlp`. YouTube changes often, and recent
  yt-dlp releases may also need a JavaScript runtime such as Deno (see the yt-dlp docs).
- **Captions use the wrong font**: install the font on your system and set `captions.font`
  to its exact family name.

## Limitations

- Heuristic and LLM scoring approximate "viral"; they don't replicate Opus Clip's trained model.
- Center-crop framing doesn't track faces or speakers (use `blur_fit` when the subject isn't centered).
- No B-roll or emoji insertion yet.
- Only content you have the rights to repurpose should be processed.
