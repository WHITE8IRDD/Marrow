"""Stage-time predictions with history. Predicts remaining seconds; learns per machine."""
import json
import statistics
import time
from pathlib import Path

ORDER = ["download", "audio", "transcribe", "score", "render"]


class Eta:
    def __init__(self, src_dur, clips, clip_len, use_llm, store):
        self.store, self.t0 = Path(store), time.time()
        h = self._load()
        d = src_dur or 600
        self.pred = {                                   # predicted seconds per stage (defaults are for THIS machine; history refines them)
            "download": h.get("download_per_s", 0.03) * d,
            "audio": h.get("audio_per_s", 0.004) * d,
            "transcribe": d / h.get("transcribe_x", 12.0),
            "score": h.get("score_s", 40.0) if use_llm else 3.0,
            "render": clips * clip_len / h.get("render_x", 5.0),
        }
        self.frac = {s: 0.0 for s in ORDER}
        self.started, self.spent = {}, {}
        self.cur, self.ema = None, None
        self.dur, self.clips, self.clip_len = d, clips, clip_len

    def update(self, key, sub):                         # key in ORDER, sub = progress of THAT stage 0..1
        now = time.time()
        if key != self.cur:
            if self.cur:
                self.frac[self.cur] = 1.0
                self.spent[self.cur] = now - self.started[self.cur]
            self.cur = key
            self.started[key] = now
        self.frac[key] = max(self.frac[key], min(float(sub), 1.0))

    def remaining(self):
        now, rem = time.time(), 0.0
        for s in ORDER:
            f, p = self.frac[s], self.pred[s]
            if s == self.cur and f > 0.05:              # measured speed of the running stage beats the guess
                p = (now - self.started[s]) / f
            rem += p * (1 - f)
        self.ema = rem if self.ema is None else 0.7 * self.ema + 0.3 * rem
        return max(0.0, self.ema)

    def finish(self):                                   # persist what really happened -> better next time
        if self.cur:
            self.spent[self.cur] = time.time() - self.started[self.cur]
        h = self._load()

        def push(k, v):
            h.setdefault("_" + k, []).append(v)
            h["_" + k] = h["_" + k][-10:]
            h[k] = statistics.median(h["_" + k])

        s = self.spent
        if "download" in s:
            push("download_per_s", s["download"] / self.dur)
        if "audio" in s:
            push("audio_per_s", s["audio"] / self.dur)
        if "transcribe" in s and s["transcribe"] > 0:
            push("transcribe_x", self.dur / s["transcribe"])
        if "score" in s:
            push("score_s", s["score"])
        if "render" in s and s["render"] > 0:
            push("render_x", self.clips * self.clip_len / s["render"])
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps(h), encoding="utf-8")

    def _load(self):
        try:
            return json.loads(self.store.read_text(encoding="utf-8"))
        except Exception:
            return {}
