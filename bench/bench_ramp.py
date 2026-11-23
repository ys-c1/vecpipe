#!/usr/bin/env python3
"""两档色标的分段数、耗时与逐像素手算参考色差上界。

用法：python3 bench/bench_ramp.py
纯标准库；生产路径（LUT 查表）与 tests/reference.py 的独立逐像素
手算实现对照，报告 CIEDE2000 最大色差与最大 sRGB 灰阶差。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vecpipe.shading import GradientRamp  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))
import reference  # noqa: E402

# 两档：3 色标（最小的多色标档）与 10 色标。位置严格递增但刻意不等距，
# 覆盖陡段、变号（极值点）等最坏情形。
GRAY_STOPS = [
    [(0.0, 0), (0.5, 128), (1.0, 255)],
    [(0.0, 0), (0.07, 230), (0.21, 40), (0.38, 190), (0.49, 70),
     (0.63, 250), (0.74, 20), (0.86, 160), (0.93, 110), (1.0, 255)],
]
RGB_STOPS = [
    [(0.0, (5, 10, 200)), (0.5, (240, 200, 30)), (1.0, (250, 250, 245))],
    [(0.0, (0, 0, 0)), (0.07, (255, 30, 20)), (0.21, (20, 240, 60)),
     (0.38, (40, 60, 250)), (0.49, (240, 240, 20)), (0.63, (250, 20, 240)),
     (0.74, (10, 250, 250)), (0.86, (200, 120, 40)), (0.93, (90, 90, 90)),
     (1.0, (255, 255, 255))],
]

WIDTH = HEIGHT = 512
REPEATS = 20
LUT_SIZE = 8192


def time_ramp(stops):
    # 建表（含 sRGB 转换、FC 切线、Hermite、LUT）。
    t0 = time.perf_counter()
    for _ in range(REPEATS):
        ramp = GradientRamp(stops, lut_size=LUT_SIZE)
    build = (time.perf_counter() - t0) / REPEATS

    image = [[1] * WIDTH for _ in range(HEIGHT)]
    t0 = time.perf_counter()
    for _ in range(REPEATS):
        ramp.apply([row[:] for row in image])
    apply_s = (time.perf_counter() - t0) / REPEATS
    return ramp, build, apply_s


def main():
    print("图像 %dx%d，LUT=%d 级，每档计时 %d 次取均值"
          % (WIDTH, HEIGHT, LUT_SIZE, REPEATS))
    print("=" * 78)
    for label, sets in (("灰度", GRAY_STOPS), ("RGB", RGB_STOPS)):
        for stops in sets:
            n = len(stops)
            ramp, build, apply_s = time_ramp(stops)
            max_e, max_g, body_e, body_g = reference.max_color_diff(
                stops, ramp.lookup, samples=8192)
            pixels = WIDTH * HEIGHT
            print("[%s %d 色标] 分段数=%d" % (label, n, n - 1))
            print("  建表耗时:   %9.3f ms/张" % (build * 1000.0))
            print("  着色耗时:   %9.3f ms/张  (%.1f 万像素, %.2f ns/像素)"
                  % (apply_s * 1000.0, pixels / 1e4,
                     apply_s / pixels * 1e9))
            print("  ramp 误差:   ΔE00=%.4f  最大 sRGB 级差=%.3f（排除近黑）"
                  % (body_e, body_g))
            print("  全区间上界: ΔE00=%.4f  最大 sRGB 级差=%.3f"
                  % (max_e, max_g))
            print("               （近黑端 ΔE 为 8bit sRGB 码值固有量化，"
                  "非 ramp 误差）")
            print("-" * 78)


if __name__ == "__main__":
    main()
