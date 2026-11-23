"""端帽基准：两档线宽，报端帽像素（相对齐头的新增覆盖）与 stroke 耗时。

用法：python3 -I bench/bench_caps.py [输出路径]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vecpipe import geom  # noqa: E402

# 固定采样窗：与线宽无关，保证两档线宽、三种端帽在同一坐标系下比较
WINDOW = (0.0, 0.0, 64.0, 32.0)  # minx, miny, maxx, maxy
LINE = [(10.0, 16.0), (54.0, 16.0)]
WIDTHS = (4.0, 12.0)
SUPERSAMPLE = 2
TIMED_POINTS = 64
TIMED_ROUNDS = 2000


def coverage(points, window, supersample):
    """窗口内被轮廓覆盖的像素数（超采样多数决）。"""
    minx, miny, maxx, maxy = window
    cols, rows = 64, 32
    on = 0
    for row in range(rows):
        for col in range(cols):
            hit = 0
            for sj in range(supersample):
                for si in range(supersample):
                    px = minx + (col + (si + 0.5) / supersample) * (maxx - minx) / cols
                    py = miny + (row + (sj + 0.5) / supersample) * (maxy - miny) / rows
                    if geom.point_in_poly(points, px, py):
                        hit += 1
            if hit * 2 > supersample * supersample:
                on += 1
    return on


def time_stroke(points, width, cap, rounds):
    start = time.perf_counter()
    for _ in range(rounds):
        geom.stroke(points, width, cap=cap)
    return (time.perf_counter() - start) / rounds * 1e6  # us/次


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    lines = []
    lines.append("端帽基准：窗口 %s，折线 %s，超采样 %d" % (WINDOW, LINE, SUPERSAMPLE))
    timed = geom.flatten((0, 0), (20, 40), (40, -20), (60, 10), TIMED_POINTS - 1)
    for w in WIDTHS:
        butt = geom.stroke(LINE, w)
        base = coverage(butt, WINDOW, SUPERSAMPLE)
        lines.append("线宽 %.1f：齐头覆盖 %d 像素" % (w, base))
        for cap in ("square", "round"):
            outline = geom.stroke(LINE, w, cap=cap)
            cap_px = coverage(outline, WINDOW, SUPERSAMPLE) - base
            area = geom.polygon_area(outline) - geom.polygon_area(butt)
            expect = geom.cap_area(w, cap)
            bound = geom.cap_area_error_bound(w, cap)
            us = time_stroke(timed, w, cap, TIMED_ROUNDS)
            lines.append(
                "  cap=%-6s 端帽像素 %5d | 轮廓面积 %.4f 手算 %.4f 差 %.2e (上界 %.2e) | %.1f us/次"
                % (cap, cap_px, area, expect, abs(area - expect), bound, us))
        us = time_stroke(timed, w, "butt", TIMED_ROUNDS)
        lines.append("  cap=butt   端帽像素     0 | 无端帽 | %.1f us/次" % us)
    report = "\n".join(lines)
    print(report)
    if out_path:
        Path(out_path).write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
