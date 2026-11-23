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


def _legacy_stroke(points, width):
    """改动前的 stroke 实现，用于逐字节对照。"""
    half = width * 0.5
    left, right = [], []
    for i, (x, y) in enumerate(points):
        if i + 1 < len(points):
            dx = points[i + 1][0] - x
            dy = points[i + 1][1] - y
        else:
            dx = x - points[i - 1][0]
            dy = y - points[i - 1][1]
        norm = math.hypot(dx, dy)
        if norm < 1e-12:
            raise ValueError("折线出现重复点")
        nx, ny = -dy / norm * half, dx / norm * half
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    return left + right[::-1]


def test_stroke_butt_identical_to_legacy():
    pts = geom.flatten((0, 0), (3, 8), (9, -4), (12, 6), 12)
    for w in (0.5, 2.0, 7.3):
        assert geom.stroke(pts, w) == _legacy_stroke(pts, w)
        assert geom.stroke(pts, w, cap="butt") == _legacy_stroke(pts, w)


def test_stroke_rejects_bad_cap():
    with pytest.raises(ValueError):
        geom.stroke([(0, 0), (1, 0)], 1.0, cap="triangle")


def test_stroke_duplicate_reports_index():
    pts = [(0, 0), (1, 0), (2, 0), (2, 0), (3, 0)]
    with pytest.raises(ValueError) as exc:
        geom.stroke(pts, 1.0)
    assert "2" in str(exc.value) and "3" in str(exc.value)


def test_stroke_cap_vertex_counts():
    pts = [(0, 0), (10, 0)]
    n = len(geom.stroke(pts, 2.0))
    assert len(geom.stroke(pts, 2.0, cap="square")) == n + 4
    assert len(geom.stroke(pts, 2.0, cap="round", cap_segments=8)) == n + 14


def test_stroke_square_cap_area_matches_hand():
    # 直线段：主体面积 = 长 * 宽，方帽手算面积 = 宽^2
    pts = [(0, 0), (20, 0)]
    w = 4.0
    outline = geom.stroke(pts, w, cap="square")
    expect = 20 * w + geom.cap_area(w, "square")
    assert abs(geom.polygon_area(outline) - expect) < 1e-9


def test_stroke_round_cap_area_within_bound():
    # 圆帽手算面积 = pi * w^2 / 4，弦逼近误差不超过 cap_area_error_bound
    pts = [(0, 0), (20, 0)]
    w = 4.0
    for k in (8, 32, 128):
        outline = geom.stroke(pts, w, cap="round", cap_segments=k)
        expect = 20 * w + geom.cap_area(w, "round")
        diff = abs(geom.polygon_area(outline) - expect)
        assert diff <= geom.cap_area_error_bound(w, "round", k)


def test_stroke_round_cap_tip_extends_by_half():
    pts = [(0, 0), (20, 0)]
    w = 4.0
    outline = geom.stroke(pts, w, cap="round", cap_segments=64)
    xs = [p[0] for p in outline]
    assert max(xs) == pytest.approx(20 + w / 2, abs=1e-9)
    assert min(xs) == pytest.approx(-w / 2, abs=1e-9)


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
