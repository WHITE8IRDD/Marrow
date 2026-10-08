"""Parse an .ass file and fail if two Dialogue lines overlap in time.

Usage:  python scripts/ass_check.py clip.ass [more.ass ...]
"""
import re
import sys

TS = re.compile(r"(\d+):(\d\d):(\d\d)\.(\d\d)")


def to_sec(t):
    m = TS.fullmatch(t.strip())
    if not m:
        raise ValueError(f"Bad ASS timestamp: {t!r}")
    h, mi, s, cs = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(cs) / 100


def check_file(path):
    evs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("Dialogue:"):
                parts = line.rstrip("\n").split(",", 9)
                evs.append((to_sec(parts[1]), to_sec(parts[2]), parts[9] if len(parts) > 9 else ""))
    evs.sort()
    errs = []
    for (s1, e1, t1), (s2, e2, t2) in zip(evs, evs[1:]):
        if s2 < e1 - 1e-9:
            errs.append(f"overlap {s1:.2f}-{e1:.2f} vs {s2:.2f}-{e2:.2f}: {t1[:40]!r}")
    return errs


def check_starts(path, min_gap=0.15):
    """No two caption events on the same style may start closer than min_gap."""
    starts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("Dialogue:"):
                parts = line.rstrip("\n").split(",", 9)
                starts.append(to_sec(parts[1]))
    starts.sort()
    errs = []
    for a, b in zip(starts, starts[1:]):
        if b - a < min_gap - 1e-9:
            errs.append(f"starts too close: {a:.2f}s and {b:.2f}s (< {min_gap}s)")
    return errs


def main(argv):
    bad = False
    gaps = False
    paths = []
    for a in argv[1:]:
        if a.startswith("--min-start-gap="):
            gaps = True
            gap = float(a.split("=", 1)[1])
        else:
            paths.append(a)
    for p in paths:
        errs = check_file(p)
        if gaps:
            errs += check_starts(p, gap)
        print(f"{p}: {'OK' if not errs else 'FAIL'}")
        for e in errs:
            print("  " + e)
        bad = bad or bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
