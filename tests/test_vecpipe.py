import math
import os
import random
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


def _near_scene(count, seed=3):
    rnd = random.Random(seed)
    pts = []
    while len(pts) < count:
        x = rnd.uniform(0.0, 200.0)
        y = rnd.uniform(0.0, 200.0)
        pts.append((x, y))
        for _ in range(rnd.randint(0, 2)):
            if len(pts) < count:
                pts.append((x + rnd.uniform(-2e-4, 2e-4),
                            y + rnd.uniform(-2e-4, 2e-4)))
    rnd.shuffle(pts)
    return pts


def test_dedup_keeps_first_representative():
    tol = 1e-3
    pts = [(0.0, 0.0), (tol * 0.5, 0.0), (5.0, 5.0),
           (tol * 0.9, tol * 0.2), (5.0 + tol * 0.3, 5.0)]
    kept, groups = geom.dedup(pts, tol)
    assert kept == [(0.0, 0.0), (5.0, 5.0)]
    assert groups == [[0, 1, 3], [2, 4]]
    assert kept[0] is pts[0] and kept[1] is pts[2]


def test_dedup_rejects_non_positive_tolerance():
    for bad in (0, -1e-9, -3):
        with pytest.raises(ValueError):
            geom.dedup([(0, 0), (1, 1)], bad)


def test_dedup_rejects_bad_tolerance_type():
    for bad in ("0.1", None, True, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            geom.dedup([(0, 0)], bad)


def test_dedup_empty():
    assert geom.dedup([], 0.1) == ([], [])


@pytest.mark.parametrize("tol", [1e-6, 1e-3, 0.5])
def test_dedup_matches_bruteforce_and_no_missed_merges(tol):
    pts = _near_scene(1200, seed=11)
    kept, groups = geom.dedup(pts, tol)
    bkept, bgroups = geom.dedup_bruteforce(pts, tol)
    assert kept == bkept
    assert groups == bgroups
    assert geom.count_missed_merges(pts, tol, groups) == 0


def test_dedup_deviation_within_bound():
    tol = 1e-3
    pts = _near_scene(800, seed=5)
    kept, groups = geom.dedup(pts, tol)
    stats = geom.dedup_stats(pts, tol, groups)
    assert stats["kept"] == len(kept)
    assert stats["kept"] < stats["input"]
    assert stats["max_deviation"] <= stats["deviation_bound"]
    # 上界必须可独立复算：tol * (最大组大小 - 1)。
    biggest = max(len(g) for g in groups)
    assert stats["deviation_bound"] == pytest.approx(tol * (biggest - 1))


def test_dedup_reduces_scene_and_culls_misses():
    scene = [
        [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0), (10.0, 1e-4),
         (10.0, 10.0), (0.0, 10.0), (0.0, 10.0)],
        [(2.0, 2.0), (2.0 + 5e-5, 2.0), (6.0, 2.0), (6.0, 6.0)],
    ]
    out, stats = pipeline.dedup_scene(scene, 1e-3)
    assert stats["input"] == 11
    assert stats["kept"] == 7
    assert stats["saved"] == 4
    assert stats["max_deviation"] <= stats["deviation_bound"]
    assert out[0][0] == (0.0, 0.0)
    # 每个多边形仍至少三个顶点。
    assert all(len(poly) >= 3 for poly in out)


def test_dedup_scene_rejects_tolerance_magnitude():
    scene = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]]
    for bad in (0, -1):
        with pytest.raises(ValueError):
            pipeline.dedup_scene(scene, bad)


def test_config_dedup_tolerance_validation():
    assert config.parse({})["dedup_tolerance"] is None
    assert config.parse({"dedup_tolerance": None})["dedup_tolerance"] is None
    assert config.parse({"dedup_tolerance": 0.01})["dedup_tolerance"] == 0.01
    for bad in (0, -1, True, "x", float("nan")):
        with pytest.raises(config.ConfigError):
            config.parse({"dedup_tolerance": bad})


def test_dedup_disabled_is_byte_identical():
    scene = [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        [(2.0000001, 2.0), (6.0, 2.0), (6.0, 6.0), (2.0, 6.0)],
    ]
    cfg = {"width": 20, "height": 20, "scale": 1.3, "rotate": 0.2,
           "gamma": 1.7, "blur": 1, "supersample": 2}
    base = pipeline.run(scene, cfg)
    assert pipeline.prepare_scene(scene, config.parse(cfg)) == (scene, None)
    # 显式传 None / 不传该字段，渲染结果逐字节一致。
    for extra in ({}, {"dedup_tolerance": None}):
        got = pipeline.run(scene, dict(cfg, **extra))
        assert got == base
    # 场景对象本身没有被改写。
    assert scene[0][2] == (10.0, 0.0)


def test_dedup_disabled_pgm_bytes_identical():
    scene = [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        [(2.0000001, 2.0), (6.0, 2.0), (6.0, 6.0), (2.0, 6.0000001)],
    ]
    cfg = {"width": 18, "height": 18, "supersample": 3}
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, extra in enumerate(({}, {"dedup_tolerance": None})):
            image = pipeline.run(scene, dict(cfg, **extra))
            path = os.path.join(tmp, "a%d.pgm" % i)
            raster.save_pgm(path, image)
            paths.append(path)
        assert open(paths[0], "rb").read() == open(paths[1], "rb").read()


def test_cli_dedup_flag_reports_counts(capsys):
    from vecpipe import cli
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "x.pgm")
        code = cli.main(["render", "--config", '{"width":8,"height":8}',
                         "--out", out, "--dedup-tolerance", "0.01"])
        assert code == 0
        text = capsys.readouterr().out
        assert "vertices=" in text and "on=" in text
        assert os.path.getsize(out) > 0


def test_cli_rejects_zero_tolerance(capsys):
    from vecpipe import cli
    code = cli.main(["render", "--dedup-tolerance", "0",
                     "--out", os.devnull])
    assert code == 2
    assert "dedup_tolerance" in capsys.readouterr().err


