"""容差去重基准：两档点数，报去重后数量与耗时，并与暴力配对对照。

用法：
    python3 bench_dedup.py            # 默认 10k / 200k
    python3 bench_dedup.py 5000 50000
"""
import random
import sys
import time

from vecpipe import geom

TOL = 1e-3


def make(n, seed):
    """模拟真实输入：大量近似重合点 + 少量完全相同点。"""
    rnd = random.Random(seed)
    pts = []
    while len(pts) < n:
        x = rnd.uniform(0.0, 2000.0)
        y = rnd.uniform(0.0, 2000.0)
        pts.append((x, y))
        for _ in range(rnd.randint(0, 2)):
            if len(pts) < n:
                pts.append((x + rnd.uniform(-2e-4, 2e-4),
                            y + rnd.uniform(-2e-4, 2e-4)))
    for _ in range(n // 20):          # 约 5% 精确重复
        pts.append(pts[rnd.randrange(len(pts))])
    rnd.shuffle(pts)
    return pts


def best_of(fn, *args, repeat=3):
    best = float("inf")
    out = None
    for _ in range(repeat):
        start = time.perf_counter()
        out = fn(*args)
        best = min(best, time.perf_counter() - start)
    return out, best


def main(argv):
    sizes = [int(a) for a in argv[1:]] or [10_000, 200_000]
    for n in sizes:
        pts = make(n, 2024)
        (kept, groups), spatial = best_of(geom.dedup, pts, TOL)
        stats = geom.dedup_stats(pts, TOL, groups)
        print("points=%d kept=%d saved=%d spatial=%.1fms "
              "max_deviation=%.3e bound=%.3e"
              % (stats["input"], stats["kept"], stats["input"] - stats["kept"],
                 spatial * 1000, stats["max_deviation"], stats["deviation_bound"]))
        if len(pts) <= 20_000:
            missed = geom.count_missed_merges(pts, TOL, groups)
            (bkept, bgroups), brute = best_of(geom.dedup_bruteforce, pts, TOL,
                                              repeat=1)
            print("  brute=%.1fms identical=%s missed_merges=%d"
                  % (brute * 1000, (kept, groups) == (bkept, bgroups), missed))
        else:
            # O(n^2) 暴力在此规模不可行，整性由小规模档的全点对检查覆盖。
            print("  brute=skipped（%d^2 对不可行）；整性由小规模档验证"
                  % len(pts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
