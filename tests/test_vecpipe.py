import math
import os
import tempfile

import pytest

from vecpipe import config, contour, geom, post, pipeline, raster, shading


def test_bezier_endpoints():
    p = geom.bezier((0, 0), (0, 1), (1, 1), (1, 0), 0.0)
    assert p == (0.0, 0.0)
    q = geom.bezier((0, 0), (0, 1), (1, 1), (1, 0), 1.0)
    assert q == (1.0, 0.0)


def test_flatten_length():
    pts = geom.flatten((0, 0), (0, 10), (10, 10), (10, 0), 8)
    assert len(pts) == 9
    assert geom.polyline_length(pts) > 10


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


# ---------- 轮廓：方格跟踪 vs 逐像素边界 ----------

def _img(mask):
    return [[255 if v else 0 for v in row] for row in mask]


def _disk(size, radius):
    mask = [[False] * size for _ in range(size)]
    center = (size - 1) / 2.0
    for r in range(size):
        for c in range(size):
            if (r - center) ** 2 + (c - center) ** 2 <= radius ** 2:
                mask[r][c] = True
    return mask


def test_contour_empty_raises():
    with pytest.raises(contour.ContourError, match="图为空"):
        contour.trace_contours([[0] * 8 for _ in range(8)])


def test_contour_full_raises():
    with pytest.raises(contour.ContourError, match="图全填满"):
        contour.trace_contours([[255] * 8 for _ in range(8)])


def test_contour_disk_is_ordered_and_inclusive():
    mask = _disk(32, 10)
    report = contour.analyze(_img(mask))
    # 一条闭合有序轮廓，相邻点 4-相邻，无跳跃
    assert report["contours"] == 1
    outline = report["contours_detail"][0]
    for a, b in zip(outline, outline[1:]):
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
    # 包含关系 B4 ⊆ T ⊆ B8，且圆盘上 T 恰好等于 B8
    assert report["inclusion_holds"]
    assert report["traced_pixels"] == report["boundary8_pixels"]
    assert not report["b4_minus_trace"]
    assert not report["trace_minus_b8"]


def test_contour_isolated_pixels_are_single_point_contours():
    mask = [[True, False, True],
            [False, False, False],
            [True, False, True]]
    contours = contour.trace_contours(_img(mask))
    assert len(contours) == 4
    assert all(len(c) == 1 for c in contours)


def test_contour_hole_produces_inner_and_outer():
    size = 32
    mask = [[False] * size for _ in range(size)]
    center = (size - 1) / 2.0
    for r in range(size):
        for c in range(size):
            d2 = (r - center) ** 2 + (c - center) ** 2
            if 6 ** 2 <= d2 <= 13 ** 2:
                mask[r][c] = True
    report = contour.analyze(_img(mask))
    assert report["contours"] >= 2  # 外边界 + 孔洞内边界
    assert report["inclusion_holds"]


def test_contour_bound_inclusion_random():
    import random
    random.seed(42)
    checked = 0
    for _ in range(300):
        h, w = random.randint(1, 12), random.randint(1, 12)
        mask = [[random.random() < 0.5 for _ in range(w)] for _ in range(h)]
        try:
            report = contour.analyze(_img(mask))
        except contour.ContourError:
            continue
        checked += 1
        assert report["inclusion_holds"]
        assert report["bound_holds"]
        k = report["contours"]
        b = report["boundary_pixels"]
        assert report["vertex_upper_bound"] == 4 * k * b
        assert report["vertex_diff_bound"] == (4 * k - 1) * b
        assert report["max_visits"] <= 4
    assert checked > 100


def test_contour_analyze_timing_fields_present():
    report = contour.analyze(_img(_disk(24, 8)))
    assert report["pixel_seconds"] >= 0
    assert report["trace_seconds"] >= 0
    text = contour.format_report(report)
    assert "B4" in text and "上界" in text


def test_config_trace_must_be_bool():
    with pytest.raises(config.ConfigError):
        config.parse({"trace": "yes"})
    assert config.parse({"trace": True})["trace"] is True
    assert config.parse({})["trace"] is False


def test_trace_off_output_byte_identical(tmp_path):
    scene = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]
    cfg = {"width": 32, "height": 32, "supersample": 2}
    img_a = pipeline.run(scene, dict(cfg, trace=False))
    img_b = pipeline.run(scene, dict(cfg, trace=True))
    path_a = os.path.join(tmp_path, "a.pgm")
    path_b = os.path.join(tmp_path, "b.pgm")
    raster.save_pgm(path_a, img_a)
    raster.save_pgm(path_b, img_b)
    assert open(path_a, "rb").read() == open(path_b, "rb").read()
