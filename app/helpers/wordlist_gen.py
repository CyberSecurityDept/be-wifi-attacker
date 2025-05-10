#!/usr/bin/env python3
import argparse
import random
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | gen | %(message)s")
log = logging.getLogger("gen")

LEET = {
    "a": "@",
    "i": "1",
    "s": "$",
    "o": "0",
    "e": "3",
    "t": "7",
    "b": "8",
    "g": "6",
    "l": "1",
    "z": "2",
}
KEYBOARD = "qwertyuiopasdfghjklzxcvbnm"
MID = list("!@#$%&*?0123456789")


def a2at(s):
    return "".join("@" if c.lower() == "a" else c for c in s)


def repeat_symbols(core, sy, Rp):
    for c1 in sy:
        for n1 in range(1, Rp + 1):
            t1 = c1 * n1
            yield core + t1
            for c2 in sy:
                for n2 in range(1, Rp + 1):
                    yield core + t1 + (c2 * n2)


def keyboard_walk(n=4):
    s = random.choice(KEYBOARD)
    idx = KEYBOARD.index(s)
    d = random.choice([-1, 1])
    for _ in range(n - 1):
        idx = (idx + d) % len(KEYBOARD)
        s += KEYBOARD[idx]
    return s


def build_target(names, y):
    return f"{a2at(names[0].title())}{y}@@!!"


def base_variants(w):
    vs = {w.lower(), w.lower().capitalize(), w.title()}
    return vs | {a2at(v) for v in vs}


def cli():
    p = argparse.ArgumentParser("gen")
    p.add_argument("--names", nargs="+", required=True)
    for b in [
        "subconscious",
        "temporal-spatial",
        "cultural-identity",
        "digital-rituals",
        "psych-weak-spots",
        "identity-layering",
        "tags",
    ]:
        p.add_argument(f"--{b}", nargs="+", default=[])
    p.add_argument("--year-from", type=int, default=2025)
    p.add_argument("--year-to", type=int, default=2025)
    p.add_argument(
        "--numeric-suffixes",
        nargs="+",
        default=["123", "1234", "2022", "2023", "2024", "2025"],
    )
    p.add_argument("--extra-suffixes", nargs="+", default=["abc"])
    p.add_argument("--symset", default="@!?#")
    p.add_argument("--symrep", type=int, default=2)
    p.add_argument("--wifi-min", type=int, default=8)
    p.add_argument("--wifi-max", type=int, default=63)
    p.add_argument("--max-size-mb", type=float, default=0.0)
    p.add_argument("--output", default="wordlist.txt")
    p.add_argument("--mangling", nargs="+", default=["title", "upper", "altcase"])
    return p.parse_args()


def main():
    args = cli()
    random.seed(0)
    years = [str(y) for y in range(args.year_from, args.year_to + 1)]
    infl = (
        args.subconscious
        + args.temporal_spatial
        + args.cultural_identity
        + args.digital_rituals
        + args.psych_weak_spots
        + args.identity_layering
    )

    log.info("Building pool …")
    mn, mx = args.wifi_min, args.wifi_max
    sym, argsym = args.symset, args.symrep
    pool = set()
    for w in args.names:
        for base in base_variants(w):
            if mn <= len(base) <= mx:
                pool.add(base)
            for y in years:
                core = f"{base}{y}"
                pool.add(core)
                pool.update(v for v in repeat_symbols(core, sym, argsym) if mn <= len(v) <= mx)
            for sfx in args.extra_suffixes + args.numeric_suffixes:
                core = f"{base}{sfx}"
                pool.add(core)
                if sfx in args.numeric_suffixes:
                    pool.update(v for v in repeat_symbols(core, sym, argsym) if mn <= len(v) <= mx)
            for inf in infl:
                pool.update({inf + base, base + inf})
    pool = list(pool)
    target = build_target(args.names, years[-1])
    if target not in pool:
        pool.insert(0, target)
    log.info("Pool size %s", len(pool))

    maxb = int(args.max_size_mb * 1024 * 1024)
    lines, used = [], 0
    for w in pool:
        ln = w + "\n"
        bl = len(ln.encode())
        if maxb and used + bl > maxb:
            break
        lines.append(ln)
        used += bl
    total = len(lines)
    log.info("Writing %s lines → %s", total, args.output)

    bar, step = 40, max(1, total // 100)
    t0 = time.time()
    with open(args.output, "w") as fh:
        for i, ln in enumerate(lines, 1):
            fh.write(ln)
            if i % step == 0 or i == total:
                pct = i * 100 // total
                fill = pct * bar // 100
                sys.stdout.write(f"\rPROG {pct:3d} [{'#'*fill}{'-'*(bar-fill)}]")
                sys.stdout.flush()
    sys.stdout.write("\n")
    log.info("✓ %s lines (%.1f KB) in %.2fs", total, used / 1024, time.time() - t0)


if __name__ == "__main__":
    main()
