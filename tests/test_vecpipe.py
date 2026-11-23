import math
import os
import tempfile

import pytest

from vecpipe import atlas, config, geom, post, pipeline, raster, shading


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


def test_atlas_hand_baseline_is_input_order():
    tiles = [{"id": "a", "w": 10, "h": 10},
             {"id": "b", "w": 10, "h": 30},
             {"id": "c", "w": 60, "h": 5}]
    out = atlas.report(tiles, 64, 4096, pack=False)
    assert [p["id"] for p in out["placements"]] == ["a", "b", "c"]
    # next-fit：c 放不下当前货架，另起一行，货架高由 b 决定。
    assert out["placements"][0]["y"] == 0
    assert out["placements"][1]["y"] == 0
    assert out["placements"][2]["y"] == 30
    assert out["stats"]["used_height"] == 35


def test_atlas_pack_sorts_by_height_descending():
    tiles = [{"id": "low", "w": 64, "h": 4},
             {"id": "tall", "w": 64, "h": 32},
             {"id": "mid", "w": 64, "h": 16}]
    out = atlas.report(tiles, 128, 4096)
    by_id = {p["id"]: p for p in out["placements"]}
    # 高度降序入箱：tall 先放。
    assert by_id["tall"]["order"] < by_id["mid"]["order"] < by_id["low"]["order"]
    assert by_id["tall"]["y"] <= by_id["mid"]["y"] <= by_id["low"]["y"]


def test_atlas_equal_height_keeps_input_order():
    tiles = [{"id": "a", "w": 64, "h": 16},
             {"id": "b", "w": 64, "h": 16}]
    out = atlas.report(tiles, 256, 4096)
    by_id = {p["id"]: p for p in out["placements"]}
    assert by_id["a"]["order"] < by_id["b"]["order"]


def test_atlas_pack_beats_hand_by_twenty_percent():
    tiles = [{"id": "t%d" % i, "w": 8 + (i * 16) % 56, "h": 8 + (i * 24) % 48}
             for i in range(40)]
    out = atlas.report(tiles, 128, 4096)
    assert out["comparison"]["reduction"] >= 0.2
    assert out["comparison"]["meets_target"]


def test_atlas_turning_off_packing_is_baseline():
    tiles = [{"id": "t%d" % i, "w": 8 + (i * 8) % 24, "h": 8 + (i * 8) % 40}
             for i in range(12)]
    off = atlas.report(tiles, 128, 4096, pack=False)
    hand = atlas.report(tiles, 128, 4096)["hand"]
    assert atlas.format_layout(off["placements"]) == \
        atlas.format_layout(hand["placements"])


def test_atlas_rejects_oversize_tile_with_id():
    tiles = [{"id": "ok", "w": 8, "h": 8},
             {"id": "huge", "w": 200, "h": 8}]
    with pytest.raises(atlas.AtlasError) as info:
        atlas.report(tiles, 128, 4096)
    assert info.value.tile_id == "huge"
    assert info.value.index == 2
    assert "huge" in str(info.value)


def test_atlas_rejects_tile_taller_than_bin():
    tiles = [{"id": "tall", "w": 8, "h": 9999}]
    with pytest.raises(atlas.AtlasError) as info:
        atlas.report(tiles, 128, 512)
    assert info.value.tile_id == "tall"


def test_atlas_rejects_duplicate_id():
    tiles = [{"id": "dup", "w": 8, "h": 8},
             {"id": "dup", "w": 16, "h": 16}]
    with pytest.raises(atlas.AtlasError) as info:
        atlas.report(tiles, 128, 4096)
    assert info.value.tile_id == "dup"
    assert info.value.index == 2


def test_atlas_rejects_zero_and_negative_size():
    for bad in ({"id": "z", "w": 0, "h": 8}, {"id": "n", "w": 8, "h": -1}):
        with pytest.raises(atlas.AtlasError) as info:
            atlas.report([bad], 128, 4096)
        assert info.value.tile_id == bad["id"]


def test_atlas_rejects_empty_and_missing_fields():
    with pytest.raises(atlas.AtlasError):
        atlas.report([], 128, 4096)
    with pytest.raises(atlas.AtlasError) as info:
        atlas.report([{"id": "a", "w": 8}], 128, 4096)
    assert info.value.tile_id == "a"


def test_atlas_placements_do_not_overlap_or_exceed_bin():
    tiles = [{"id": "t%d" % i, "w": 8 + (i * 12) % 40,
              "h": 8 + (i * 20) % 56} for i in range(30)]
    out = atlas.report(tiles, 128, 4096)
    rects = [(p["x"], p["y"], p["w"], p["h"]) for p in out["placements"]]
    for x, y, w, h in rects:
        assert x >= 0 and y >= 0 and x + w <= 128 and y + h <= 4096
    for i in range(len(rects)):
        x1, y1, w1, h1 = rects[i]
        for j in range(i + 1, len(rects)):
            x2, y2, w2, h2 = rects[j]
            assert not (x1 < x2 + w2 and x2 < x1 + w1
                        and y1 < y2 + h2 and y2 < y1 + h1)


def test_atlas_waste_rate_matches_counts():
    tiles = [{"id": "a", "w": 32, "h": 32}, {"id": "b", "w": 32, "h": 32}]
    out = atlas.report(tiles, 128, 4096)
    used = 32 * 32 * 2
    assert out["stats"]["used_area"] == used
    expected = 1.0 - used / (128 * out["stats"]["used_height"])
    assert abs(out["stats"]["waste_rate"] - expected) < 1e-12


def test_atlas_cli_no_pack_matches_hand():
    import contextlib
    import io
    import json as _json
    import subprocess
    import sys

    tiles = [{"id": "a", "w": 32, "h": 64}, {"id": "b", "w": 96, "h": 64},
             {"id": "c", "w": 128, "h": 8}]
    args = [sys.executable, "-m", "vecpipe.cli", "atlas",
            "--tiles", _json.dumps(tiles), "--width", "128", "--height", "256"]
    packed = subprocess.run(args, capture_output=True, text=True, check=True)
    off = subprocess.run(args + ["--no-pack"], capture_output=True, text=True,
                         check=True)
    coords_off = off.stdout.splitlines()[:-1]
    assert coords_off == ["a 0 0 32 64", "b 32 0 96 64", "c 0 64 128 8"]
    # 关箱输出的坐标必须与手摆基线逐字节一致
    hand = atlas.report(tiles, 128, 256)["hand"]
    assert "\n".join(coords_off) + "\n" == atlas.format_layout(hand["placements"])


def test_atlas_cli_reports_error_and_block_id():
    import json as _json
    import subprocess
    import sys

    tiles = [{"id": "ok", "w": 8, "h": 8}, {"id": "bad", "w": 256, "h": 8}]
    proc = subprocess.run(
        [sys.executable, "-m", "vecpipe.cli", "atlas",
         "--tiles", _json.dumps(tiles), "--width", "128"],
        capture_output=True, text=True)
    assert proc.returncode == 2
    assert "bad" in proc.stderr
