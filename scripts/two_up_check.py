"""Measure how well the two-up framing centres each speaker.

Analysis picks a crop per speaker; this reports where each face actually lands
inside its own panel, because "the speaker is not centred" is a claim about
pixels, not about the plan. Offsets are a fraction of the panel's width: 0.00 is
dead centre, +/-0.50 is the panel's edge.

    python scripts/two_up_check.py podcast.mp4                     # plan only
    python scripts/two_up_check.py podcast.mp4 --render            # + real encode
    python scripts/two_up_check.py podcast.mp4 --start 12 --end 42 --shot-png out.png

Exit status is non-zero when any measured speaker sits further than --tolerance
(default 0.05) from the centre of their panel, so it can gate a check. Runs on
the source itself: with no workdir the analysis is not cached between runs.
"""
import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marrow import layout as L  # noqa: E402


def face_in(frame, det):
    """Largest face in a crop, as (cx, cy, w) or None."""
    faces = L.detect_faces(frame, det, 0.0, 0.02)
    if not faces:
        return None
    best = max(faces, key=lambda f: f[2])
    return best[0] + best[2] / 2.0, best[1] + best[3] / 2.0, best[2]


def frame_at(video, t):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def measure_plan(video, start, end, mode, workdir=None):
    """Per panel: where the speaker's face sits inside the planned crop."""
    det = L.get_detector()
    if det is None:
        raise SystemExit("OpenCV or the YuNet model is unavailable: install "
                         "opencv-python-headless (the model downloads on first use).")
    rows = []
    for shot in L.analyze(str(video), start, end, speaker_mode=mode, workdir=workdir):
        mid = (shot["start"] + shot["end"]) / 2.0
        frame = frame_at(video, mid)
        if frame is None:
            continue
        panels = shot.get("panels")
        if not panels:
            # Frame-view fallback: the frame's own two halves are the panels.
            h, w = frame.shape[:2]
            panels = [{"x": 0, "y": 0, "w": w // 2, "h": h},
                      {"x": w // 2, "y": 0, "w": w - w // 2, "h": h}]
        for i, panel in enumerate(panels[:2]):
            crop = frame[panel["y"]:panel["y"] + panel["h"],
                         panel["x"]:panel["x"] + panel["w"]]
            face = face_in(crop, det) if crop.size else None
            rows.append({
                "shot": f"{shot['start']:.2f}-{shot['end']:.2f}",
                "layout": shot["layout"] + (f"/{shot.get('views')}" if shot.get("views") else ""),
                "panel": i,
                "dx": None if face is None else (face[0] - crop.shape[1] / 2.0) / crop.shape[1],
                "dy": None if face is None else (face[1] - crop.shape[0] / 2.0) / crop.shape[0],
                "face_w": None if face is None else face[2] / crop.shape[1],
            })
    return rows


def measure_render(video, start, end, mode, platform="shorts", workdir="work/two_up_check"):
    """Render the analysed shots and measure the face in each output half."""
    from marrow import renderer
    from marrow.config import load_config

    cfg = load_config()
    cfg["render"]["speaker_mode"] = mode
    cfg["captions"]["enabled"] = False
    ry = cfg["platforms"][platform]["res_y"]
    out_dir = Path(workdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    det = L.get_detector()
    rows = []
    for i, shot in enumerate(L.analyze(str(video), start, end, speaker_mode=mode,
                                       workdir=out_dir)):
        out = out_dir / f"shot{i}.mp4"
        renderer.render_clip(video, shot["start"], shot["end"], None, out, cfg, platform,
                             layout=shot["layout"], shot=shot)
        frame = frame_at(out, max(0.1, (shot["end"] - shot["start"]) / 2.0))
        for half in (0, 1):
            crop = frame[half * (ry // 2):(half + 1) * (ry // 2)]
            face = face_in(crop, det) if crop.size else None
            rows.append({
                "shot": f"{shot['start']:.2f}-{shot['end']:.2f}",
                "layout": f"rendered half {half}",
                "panel": half,
                "dx": None if face is None else (face[0] - crop.shape[1] / 2.0) / crop.shape[1],
                "dy": None if face is None else (face[1] - crop.shape[0] / 2.0) / crop.shape[0],
                "face_w": None if face is None else face[2] / crop.shape[1],
            })
    return rows


def annotate(video, start, end, mode, path):
    """Write the middle frame of each shot with its panel outlines and centrelines."""
    det = L.get_detector()
    canvas_rows = []
    for shot in L.analyze(str(video), start, end, speaker_mode=mode):
        frame = frame_at(video, (shot["start"] + shot["end"]) / 2.0)
        if frame is None:
            continue
        for panel in (shot.get("panels") or [])[:2]:
            x, y, w, h = panel["x"], panel["y"], panel["w"], panel["h"]
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.line(frame, (x + w // 2, y), (x + w // 2, y + h), (0, 255, 255), 2)
            face = face_in(frame[y:y + h, x:x + w], det)
            if face:
                fx, fy = int(x + face[0]), int(y + face[1])
                cv2.drawMarker(frame, (fx, fy), (0, 0, 255), cv2.MARKER_CROSS, 30, 3)
        canvas_rows.append(frame)
    if not canvas_rows:
        raise SystemExit("no shots analysed in that range")
    max_w = max(f.shape[1] for f in canvas_rows)
    scaled = [f if f.shape[1] == max_w else cv2.resize(f, (max_w, int(f.shape[0] * max_w / f.shape[1])))
              for f in canvas_rows]
    import numpy as np

    cv2.imwrite(str(path), np.vstack(scaled))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=30.0)
    ap.add_argument("--mode", default="two_up", choices=list(L.SPEAKER_MODES))
    ap.add_argument("--tolerance", type=float, default=0.05,
                    help="how far off centre a speaker may sit (fraction of panel width)")
    ap.add_argument("--render", action="store_true",
                    help="also encode the shots and measure the rendered halves")
    ap.add_argument("--shot-png", default=None, help="write an annotated frame per shot")
    ap.add_argument("--workdir", default=None,
                    help="cache the shot analysis here (default: analyse fresh)")
    args = ap.parse_args(argv)

    if not Path(args.video).exists():
        raise SystemExit(f"no such file: {args.video}")

    rows = measure_plan(args.video, args.start, args.end, args.mode, args.workdir)
    if args.render:
        rows += measure_render(args.video, args.start, args.end, args.mode)
    if args.shot_png:
        print("wrote", annotate(args.video, args.start, args.end, args.mode, args.shot_png))

    worst, missing = 0.0, 0
    print(f"{'shot':>14}  {'layout':>18}  {'panel':>5}  {'dx':>7}  {'dy':>7}  {'face_w':>6}")
    for row in rows:
        if row["dx"] is None:
            missing += 1
            print(f"{row['shot']:>14}  {row['layout']:>18}  {row['panel']:>5}  "
                  f"{'no face':>7}")
            continue
        worst = max(worst, abs(row["dx"]))
        print(f"{row['shot']:>14}  {row['layout']:>18}  {row['panel']:>5}  "
              f"{row['dx']:>+7.3f}  {row['dy']:>+7.3f}  {row['face_w']:>6.3f}")
    print(f"\nworst |dx| = {worst:.3f} (tolerance {args.tolerance:.3f}), "
          f"{missing} panel(s) with no detectable face")
    return 1 if worst > args.tolerance else 0


if __name__ == "__main__":
    sys.exit(main())
