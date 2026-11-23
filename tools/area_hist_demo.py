"""面积分布直方图演示（独立脚本，不参与渲染管线）。

跑法：在仓库根目录执行  python3 tools/area_hist_demo.py

内容：
1. 渲染一个部分覆盖的场景，两档图块网格各出一份面积分桶直方图；
2. 逐块手算（独立代码路径）复核落桶与桶计数，给出误差上界；
3. 用鞋带公式给出矢量多边形的几何面积，与像素面积总量对照；
4. 演示负桶边 / 区间重叠的报错，报错信息带桶号。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vecpipe import geom, pipeline, stats  # noqa: E402


SCENE = [
    [(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0)],      # 左上 6x6 方块
    [(2.0, 2.0), (9.0, 2.0), (9.0, 9.0), (2.0, 9.0)],      # 偏移重叠方块
    [(7.0, 7.0), (8.0, 7.0), (8.0, 8.0), (7.0, 8.0)],      # 小方块
]


def main():
    cfg = {"width": 64, "height": 64, "supersample": 2}
    image = pipeline.run(SCENE, cfg)

    edges = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256]
    report = stats.two_tier_report(image, edges,
                                   coarse=(4, 4), fine=(16, 16))
    for label, name in (("coarse", "粗档 4x4"), ("fine", "细档 16x16")):
        print("== %s ==" % name)
        print(stats.format_report(report[label]))
        print()

    # 矢量几何面积（鞋带公式）与光栅化像素面积总量对照
    geo_total = sum(geom.polygon_area(poly) for poly in SCENE)
    px_total = sum(sum(row) for row in report["coarse"]["tile_areas"])
    print("几何面积合计（含重叠，鞋带公式）: %.3f" % geo_total)
    print("光栅点亮像素合计（粗档块面积求和）: %d" % px_total)
    print("注：场景有重叠且经超采样光栅化，两者不要求相等，仅作量级对照。")
    print()

    # 校验报错：负桶边
    for bad in ([0, 4, -1, 16], [0, 4, 4, 16]):
        try:
            stats.validate_edges(bad)
        except ValueError as exc:
            print("非法桶边 %r -> %s" % (bad, exc))


if __name__ == "__main__":
    main()
