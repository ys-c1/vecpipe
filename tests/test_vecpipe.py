import hashlib
import math
import os
import tempfile

import pytest

from vecpipe import clipstat, config, geom, post, pipeline, raster, shading
from vecpipe import cli


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


def test_clipstat_signed_area():
    ccw = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert clipstat.signed_area(ccw) == 100.0
    assert clipstat.signed_area(ccw[::-1]) == -100.0


def test_clipstat_empty_window_reports_index():
    shapes = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    windows = [[(0, 0), (1, 0), (1, 1)], [(2, 2)], [(0, 0), (5, 0), (5, 5)]]
    with pytest.raises(ValueError, match="窗口 1 为空"):
        clipstat.measure(shapes, windows, 8, 8)


def test_clipstat_negative_area_reports_index():
    shapes = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    cw = [(0, 0), (0, 5), (5, 5), (5, 0)]  # 顺时针，面积为负
    with pytest.raises(ValueError, match="窗口 1 面积为负"):
        clipstat.measure(shapes, [[(0, 0), (1, 0), (1, 1)], cw], 8, 8)


def test_clipstat_ratio_known():
    shapes = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    half = [(5, 0), (10, 0), (10, 10), (5, 10)]
    inter, union, ratio = clipstat.clip_ratio(shapes, half)
    assert inter == pytest.approx(50.0)
    assert union == pytest.approx(100.0)
    assert ratio == pytest.approx(0.5)


def test_clipstat_pixel_within_bound():
    shapes = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    window = [(2, 2), (8, 2), (8, 8), (2, 8)]
    inter, union, ratio = clipstat.clip_ratio(shapes, window)
    ei, eu, bound = clipstat.pixel_ratio(shapes, window, 24, 24)
    assert inter == pytest.approx(36.0)
    est = ei / eu
    assert abs(ratio - est) <= bound + 1e-12


def test_clipstat_two_tiers_report_ratio_and_time():
    shapes = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    bbox = (0.0, 0.0, 10.0, 10.0)
    for tier in (4, 16):
        res = clipstat.measure(shapes, clipstat.grid_windows(tier, bbox), 12, 12)
        assert res["windows"] == tier
        assert 0.0 < res["ratio"] <= 1.0
        assert res["elapsed"] >= 0.0
        assert res["max_dev"] <= res["max_window_bound"] + 1e-12
        assert abs(res["ratio"] - res["pixel_ratio"]) <= res["err_bound"] + 1e-12


def test_clipstat_rejects_bad_window_count():
    with pytest.raises(ValueError):
        clipstat.grid_windows(0, (0, 0, 1, 1))


def test_cli_clipstat_runs(capsys):
    assert cli.main(["clipstat", "--tiers", "2,4", "--pixels", "8"]) == 0
    out = capsys.readouterr().out
    assert out.count("tier windows=") == 2


def test_render_bytes_unchanged_when_stats_off():
    # 统计全部走 clipstat 子命令，render 路径不变，出图必须与基线逐字节相同
    image = pipeline.run(cli.SCENE, {})
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.pgm")
        raster.save_pgm(path, image)
        data = open(path, "rb").read()
    assert hashlib.sha256(data).hexdigest() == (
        "fbda3e5665174433272beab4f25172bc03466e3f8700bcf6007b32c3636f2dc3")
