import math
import os
import tempfile

import pytest

from vecpipe import config, geom, post, pipeline, raster, shading


def test_bezier_endpoints():
    p = geom.bezier((0, 0), (0, 1), (1, 1), (1, 0), 0.0)
    assert p == (0.0, 0.0)
    q = geom.bezier((0, 0), (0, 1), (1, 1), (1, 0), 1.0)
    assert q == (1.0, 0.0)


def test_flatten_length():
    pts = geom.flatten((0, 0), (0, 10), (10, 10), (10, 0), 8)
    assert len(pts) == 9
    assert geom.polyline_length(pts) > 10


# ---------- 自适应弦高细分 ----------

GENTLE = ((0, 0), (4, 0.2), (8, 0.2), (12, 0))
TIGHT = ((1.5, -2.25), (7.0, 0.5), (-3.25, 4.0), (9.75, 8.125))


def test_adaptive_respects_tolerance():
    for curve in (GENTLE, TIGHT):
        for tol in (0.25, 0.05):
            leaves = geom.adaptive_leaves(*curve, tol)
            # 解析上界：每个叶子都不超容差
            assert all(bound <= tol + 1e-15 for _, _, bound in leaves)
            poly = geom.adaptive_flatten(*curve, tol)
            assert len(poly) == len(leaves) + 1
            # 与 4096 段细密参考折线对照的实测最大弦高
            measured = geom.max_chord_error(*curve, poly)
            assert measured <= geom.adaptive_error_bound(*curve, tol) + 1e-12
            assert measured <= tol


def test_adaptive_smaller_tol_uses_more_segments():
    coarse = len(geom.adaptive_leaves(*TIGHT, 0.25))
    fine = len(geom.adaptive_leaves(*TIGHT, 0.01))
    assert fine > coarse
    # 缓曲线在同样容差下段数明显更少
    assert len(geom.adaptive_leaves(*GENTLE, 0.25)) < coarse


def test_adaptive_span_partition_and_endpoints():
    leaves = geom.adaptive_leaves(*TIGHT, 0.1)
    spans = [span for _, span, _ in leaves]
    assert spans == sorted(spans)
    assert spans[0][0] == 0.0 and spans[-1][1] == 1.0
    for (_l, hi), (lo2, _r) in zip(spans, spans[1:]):
        assert hi == lo2
    poly = geom.adaptive_flatten(*TIGHT, 0.1)
    assert poly[0] == geom.bezier(*TIGHT, 0.0)
    assert poly[-1] == TIGHT[3]


def test_adaptive_zero_tolerance_reports_segment():
    with pytest.raises(geom.FlattenError) as exc:
        geom.adaptive_flatten(*TIGHT, 0.0)
    assert "第 0 段" in str(exc.value)
    with pytest.raises(geom.FlattenError):
        geom.adaptive_leaves(*TIGHT, -1.0)
    with pytest.raises(geom.FlattenError):
        geom.adaptive_leaves(*TIGHT, float("nan"))


def test_adaptive_coincident_points_reports_segment():
    # 四个控制点完全重合：退化为点
    with pytest.raises(geom.FlattenError) as exc:
        geom.adaptive_flatten((5, 5), (5, 5), (5, 5), (5, 5), 0.1)
    assert "第 0 段" in str(exc.value) and "重合" in str(exc.value)
    # 仅端点重合（自交/闭环）：弦长为零，判据无定义
    with pytest.raises(geom.FlattenError) as exc:
        geom.adaptive_flatten((0, 0), (10, 0), (0, 10), (0, 0), 0.1)
    assert "第 0 段" in str(exc.value)


def test_adaptive_segment_ids_are_preorder_unique():
    leaves = geom.adaptive_leaves(*TIGHT, 0.01)
    ids = [seg_id for seg_id, _, _ in leaves]
    assert len(ids) == len(set(ids))
    # 前序编号非负；根段（0）在小容差下是内部节点，不出现在叶子中
    assert min(ids) >= 0 and max(ids) >= len(leaves)
    # 根段直接被接受时，唯一叶子编号必为 0
    single = geom.adaptive_leaves(*GENTLE, 0.25)
    assert len(single) == 1 and single[0][0] == 0
    # 递归深度即叶子数（完全二叉树），节点总数 = 2*叶子数 - 1，
    # 最大段号应不超过该上限
    assert max(ids) <= 2 * len(leaves) - 2


def test_flatten_path_global_segment_numbers():
    # 第二条曲线退化，报错段号应接续第一条曲线的节点总数
    with pytest.raises(geom.FlattenError) as exc:
        geom.flatten_path(
            [GENTLE, ((0, 0), (10, 0), (0, 10), (0, 0))],
            adaptive=True, tol=0.1)
    msg = str(exc.value)
    assert "第 3 段" in msg
    # 正常多段路径：连接处不重复加点
    pts = geom.flatten_path([GENTLE, GENTLE], adaptive=True, tol=0.25)
    assert pts[0] == GENTLE[0] and pts[-1] == GENTLE[3]
    n_single = len(geom.adaptive_flatten(*GENTLE, 0.25))
    assert len(pts) == 2 * n_single - 1


def test_disabled_adaptive_is_identical_to_flatten():
    for curve in (GENTLE, TIGHT):
        for s in (1, 4, 16):
            assert geom.flatten_curve(*curve, adaptive=False, segments=s) \
                == geom.flatten(*curve, s)
            assert geom.flatten_path([curve], adaptive=False, segments=s) \
                == geom.flatten(*curve, s)


def test_config_adaptive_fields():
    cfg = config.parse({"adaptive": True, "flatness": 0.1, "segments": 32})
    assert cfg["adaptive"] is True and cfg["flatness"] == 0.1
    assert cfg["segments"] == 32
    # 默认关闭自适应，默认值与旧行为兼容
    default = config.parse({})
    assert default["adaptive"] is False and default["segments"] == 16
    with pytest.raises(config.ConfigError):
        config.parse({"adaptive": "yes"})
    with pytest.raises(config.ConfigError):
        config.parse({"flatness": 0})
    with pytest.raises(config.ConfigError):
        config.parse({"segments": 0})


def test_pipeline_flatten_scene_wiring():
    curves = [GENTLE]
    fixed = pipeline.flatten_scene(curves, config.parse({}))
    assert fixed == geom.flatten(*GENTLE, 16)
    adaptive = pipeline.flatten_scene(
        curves, config.parse({"adaptive": True, "flatness": 0.05}))
    assert adaptive == geom.adaptive_flatten(*GENTLE, 0.05)
    with pytest.raises(geom.FlattenError):
        pipeline.flatten_scene(
            [((0, 0), (10, 0), (0, 10), (0, 0))],
            config.parse({"adaptive": True}))


def test_point_in_poly():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert geom.point_in_poly(square, 5, 5)
    assert not geom.point_in_poly(square, 15, 5)


def test_clip_convex():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    window = [(2, 2), (8, 2), (8, 8), (2, 8)]
    out = geom.clip_convex(square, window)
    assert 3 <= len(out) <= 8


def test_stroke_requires_positive_width():
    with pytest.raises(ValueError):
        geom.stroke([(0, 0), (1, 0)], 0)


def test_config_rejects_unknown():
    with pytest.raises(config.ConfigError):
        config.parse({"nope": 1})


def test_config_rejects_range():
    with pytest.raises(config.ConfigError):
        config.parse({"width": 0})


def test_config_supersample_cap():
    with pytest.raises(config.ConfigError):
        config.parse({"supersample": 9})


def test_raster_fill_half():
    image = raster.new_image(8, 8)
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    raster.fill(image, [square], 2)
    on = raster.count_on(image)
    assert 60 <= on <= 64


def test_raster_empty_export():
    with pytest.raises(ValueError):
        raster.save_pgm("x.pgm", [[]])


def test_save_and_read_bytes():
    image = raster.new_image(4, 4)
    raster.fill(image, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "a.pgm")
        raster.save_pgm(path, image)
        data = open(path, "rb").read()
        assert data.startswith(b"P5\n4 4\n255\n")
        assert len(data) == 11 + 16


def test_gamma_changes_midtones():
    image = [[128, 0], [255, 64]]
    out = post.gamma(image, 2.0)
    assert out[0][0] > 128


def test_blur_radius_zero_copies():
    image = [[1, 2], [3, 4]]
    out = post.blur(image, 0)
    assert out == image and out is not image


def test_blur_smooths():
    image = [[0, 0, 0], [0, 255, 0], [0, 0, 0]]
    out = post.blur(image, 1)
    assert out[1][1] < 255


def test_shading_modes():
    image = [[255, 0], [0, 255]]
    shading.apply(image, "flat", 0.5)
    assert image[0][0] == 127
    with pytest.raises(config.ConfigError):
        shading.apply(image, "bogus")


def test_pipeline_runs():
    scene = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    image = pipeline.run(scene, {"width": 16, "height": 16, "supersample": 2})
    assert len(image) == 16 and len(image[0]) == 16
    assert raster.count_on(image) > 0


def test_pipeline_rejects_bad_config():
    with pytest.raises(config.ConfigError):
        pipeline.run([[(0, 0), (1, 0), (1, 1)]], {"gamma": 0})
