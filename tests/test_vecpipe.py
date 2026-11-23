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


def _duplicate_scene():
    tri = [(1.0, 1.0), (9.0, 1.0), (5.0, 8.0)]
    return [list(tri), list(tri), list(tri)]


def test_cache_hit_reuses_coverage():
    scene = _duplicate_scene()
    cache = raster.CoverageCache(8)
    image = raster.new_image(16, 16)
    raster.fill(image, scene, 2, cache=cache, verify=True)
    assert cache.misses == 1
    assert cache.hits == 2
    assert cache.entries == 1
    assert cache.hit_rate == pytest.approx(2 / 3)
    assert raster.count_on(image) > 0


def test_cache_off_byte_identical_to_direct():
    scene = _duplicate_scene() + [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]
    direct = raster.new_image(24, 18)
    raster.fill(direct, scene, 2)
    cached = raster.new_image(24, 18)
    cache = raster.CoverageCache(16)
    raster.fill(cached, scene, 2, cache=cache, verify=True)
    assert cached == direct
    pgm_direct = b"".join(bytes(row) for row in direct)
    pgm_cached = b"".join(bytes(row) for row in cached)
    assert pgm_cached == pgm_direct


def test_cache_disabled_by_default_path():
    image = raster.new_image(8, 8)
    raster.fill(image, _duplicate_scene(), 2, cache=raster.CoverageCache(0))
    assert raster.count_on(image) > 0


def test_cache_verify_detects_tampered_entry():
    scene = _duplicate_scene()
    cache = raster.CoverageCache(8)
    image = raster.new_image(16, 16)
    raster.fill(image, scene, 2, cache=cache)
    slot = cache.slot_of(raster.coverage_key(scene[0]))
    r0, c0, mask = cache._slots[slot][1]
    mask[0][0] ^= 0b11
    with pytest.raises(raster.CacheVerifyError) as exc:
        raster.fill(raster.new_image(16, 16), scene, 2, cache=cache, verify=True)
    assert exc.value.differences
    assert exc.value.differences[0][0:2] == (r0, c0)


def test_cache_full_raises_with_entry():
    cache = raster.CoverageCache(2)
    mask = [[0] * 2 for _ in range(2)]
    keys = []
    i = 0
    while cache.entries < 2:
        cand = raster.coverage_key([(float(i), 0.0), (float(i) + 1, 0.0),
                                    (float(i) + 1, 1.0)])
        try:
            cache.put(cand, mask)
            keys.append(cand)
        except raster.CacheError:
            pass
        i += 1
    assert cache.entries == 2
    extra = raster.coverage_key([(900.0, 0.0), (901.0, 0.0), (901.0, 1.0)])
    with pytest.raises(raster.CacheFullError) as exc:
        cache.put(extra, mask)
    assert exc.value.capacity == 2 and exc.value.incoming_key == extra
    assert exc.value.slot == cache.home_slot(extra)


def test_cache_collision_when_probe_chain_full():
    # 构造探测链占满但表未满：容量 4，只写 3 个条目且让某键的整条
    # 探测链（主槽起的连续槽）都被其他条目占据
    cache = raster.CoverageCache(4)
    mask = [[0] * 2 for _ in range(2)]
    written = []
    i = 0
    while len(written) < 3 and i < 100000:
        cand = raster.coverage_key([(float(i), 0.0), (float(i) + 1, 0.0),
                                    (float(i) + 1, 1.0)])
        try:
            cache.put(cand, mask)
            written.append(cand)
        except raster.CacheError:
            pass
        i += 1
    assert cache.entries == 3
    # 找一个未收录键，其探测链前 4 槽（即全表）遍历不到空槽等价于表满；
    # 这里改为直接验证写满表后的冲突读取路径，并单独验证满写入
    stranger = raster.coverage_key([(900.0, 0.0), (901.0, 0.0), (901.0, 1.0)])
    # 再补一个条目把表填满
    while cache.entries < 4 and i < 200000:
        cand = raster.coverage_key([(float(i), 0.0), (float(i) + 1, 0.0),
                                    (float(i) + 1, 1.0)])
        try:
            cache.put(cand, mask)
        except raster.CacheError:
            pass
        i += 1
    assert cache.entries == 4
    # 表满：写入报 CacheFullError
    with pytest.raises(raster.CacheCollisionError):
        cache.get(stranger)
    with pytest.raises(raster.CacheFullError):
        cache.put(stranger, mask)
    assert cache.collisions >= 1


def test_cache_probe_reuses_other_slots():
    # 开放寻址：同主槽的两个不同键在容量允许时都能写入并各自命中
    cache = raster.CoverageCache(4)
    k1 = raster.coverage_key([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    k2 = None
    for i in range(2, 10000):
        cand = raster.coverage_key([(float(i), 0.0), (float(i) + 1, 0.0),
                                    (float(i) + 1, 1.0)])
        if cache.home_slot(cand) == cache.home_slot(k1):
            k2 = cand
            break
    assert k2 is not None
    m1, m2 = [[1] * 2 for _ in range(2)], [[2] * 2 for _ in range(2)]
    cache.put(k1, m1)
    cache.put(k2, m2)
    assert cache.slot_of(k1) != cache.slot_of(k2)
    assert cache.get(k1) is m1 and cache.get(k2) is m2
    assert cache.collisions == 1


def test_cache_byte_size_grows_with_entries():
    cache = raster.CoverageCache(8)
    empty = cache.byte_size
    key = raster.coverage_key([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    cache.put(key, [[0b11] * 4 for _ in range(4)])
    assert cache.byte_size > empty
    assert cache.stats()["byte_size"] == cache.byte_size


def test_pipeline_cache_config():
    scene = _duplicate_scene()
    off = pipeline.run(scene, {"width": 24, "height": 24, "cache_capacity": 0})
    on = pipeline.run(scene, {"width": 24, "height": 24,
                              "cache_capacity": 8, "cache_verify": True})
    assert off == on
    with pytest.raises(config.ConfigError):
        config.parse({"cache_capacity": -1})
    with pytest.raises(config.ConfigError):
        config.parse({"cache_verify": "yes"})
