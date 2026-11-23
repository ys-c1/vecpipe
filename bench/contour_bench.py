"""两档图幅基准：逐像素边界集合 vs 方格跟踪。

用法：python3 -I bench/contour_bench.py
两类掩膜各跑两档图幅（64、256）：
  1. 管线渲染的旋转 30° 正方形（带超采样抗锯齿的真实输出）；
  2. 二值实心圆盘（干净连通形状，展示有序长轮廓）。
每档报：B4/B8 边界像素数、轮廓数、跟踪顶点数、集合对照、
顶点差及严格上界、两法耗时（最佳 5 次）。末尾演示空图 / 全填满
报错。
"""
import math
import sys
import time

sys.path.insert(0, "/home/ys/feedback/uidreczz28d226oXWC2")

from vecpipe import contour, pipeline, raster  # noqa: E402


def rendered_square(size):
    scene = [[(-3.0, -3.0), (3.0, -3.0), (3.0, 3.0), (-3.0, 3.0)]]
    moved = [pipeline.transform(poly, 1.0, math.pi / 6,
                                size / 2.0, size / 2.0)
             for poly in scene]
    image = raster.new_image(size, size)
    raster.fill(image, moved, 2)
    return image


def binary_disk(size):
    image = [[0] * size for _ in range(size)]
    center = (size - 1) / 2.0
    radius = size * 0.35
    for r in range(size):
        for c in range(size):
            if (r - center) ** 2 + (c - center) ** 2 <= radius ** 2:
                image[r][c] = 255
    return image


def best_time(fn, rounds=5):
    best = float("inf")
    result = None
    for _ in range(rounds):
        t0 = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - t0)
    return result, best


def report_row(label, image):
    mask = contour.foreground_mask(image)  # 掩膜构造一次，两法共用
    (b4, b8), t_pixel = best_time(lambda: contour.pixel_boundary(mask))
    rep, t_trace = best_time(lambda: contour.analyze(image))
    on = raster.count_on(image)
    print("== %s  图幅 %dx%d（前景 on=%d）=="
          % (label, rep["height"], rep["width"], on))
    print("   逐像素: |B4|=%d  |B8|=%d  耗时 %.6f s"
          % (len(b4), len(b8), t_pixel))
    print("   跟踪  : %d 条有序轮廓，%d 个顶点，不同像素 %d，耗时 %.6f s"
          % (rep["contours"], rep["traced_vertices"],
             rep["traced_pixels"], t_trace))
    longest = max((len(c) for c in rep["contours_detail"]), default=0)
    print("   最长轮廓: %d 个有序顶点；单像素最多访问 %d 次（上限 4）"
          % (longest, rep["max_visits"]))
    print("   集合对照: B4-T=%d, T-B4=%d, T-B8=%d, B8-T=%d；"
          "B4⊆T⊆B8: %s"
          % (len(rep["b4_minus_trace"]), len(rep["trace_minus_b4"]),
             len(rep["trace_minus_b8"]), len(rep["b8_minus_trace"]),
             rep["inclusion_holds"]))
    print("   顶点差 |V|-|B4|=%d；上界 (4K-1)*|B4|=%d，"
          "|V|≤4K*|B4|=%d，%s\n"
          % (rep["vertex_diff"], rep["vertex_diff_bound"],
             rep["vertex_upper_bound"],
             "成立" if rep["bound_holds"] else "不成立"))


def main():
    print("两档图幅基准（阈值 128，最佳 5 次计时）\n")
    for size in (64, 256):
        report_row("渲染旋转正方形", rendered_square(size))
        report_row("二值实心圆盘  ", binary_disk(size))

    print("== 异常输入报错演示 ==")
    for label, img in (("空图", [[0] * 16 for _ in range(16)]),
                       ("全填满", [[255] * 16 for _ in range(16)])):
        try:
            contour.analyze(img)
        except contour.ContourError as exc:
            print("  %s -> ContourError: %s" % (label, exc))


if __name__ == "__main__":
    main()
