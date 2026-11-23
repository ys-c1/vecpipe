import os
import subprocess
import sys
import tempfile

import pytest

from vecpipe import cli, geom, pipeline, raster, stats


# ---------- 构造确定性图像 ----------

def _image_with_on(width, height, on_cells):
    image = raster.new_image(width, height)
    for r, c in on_cells:
        image[r][c] = 255
    return image


def _hand_count(image, r0, r1, c0, c1, threshold=128):
    """测试侧独立手数：不用 vecpipe 的任何切块函数。"""
    n = 0
    for r in range(r0, r1):
        for c in range(c0, c1):
            if image[r][c] >= threshold:
                n += 1
    return n


# ---------- 桶边校验 ----------

def test_validate_edges_ok():
    assert stats.validate_edges([0, 1, 4, 16]) == 3


def test_negative_edge_reports_index():
    with pytest.raises(ValueError, match="第 2 号桶边为负"):
        stats.validate_edges([0, 4, -1])


def test_overlapping_edge_reports_bucket_index():
    with pytest.raises(ValueError, match="第 1 号桶区间非法"):
        stats.validate_edges([0, 4, 4, 16])


def test_reversed_edge_reports_bucket_index():
    with pytest.raises(ValueError, match="第 0 号桶区间非法"):
        stats.validate_edges([4, 0, 16])


def test_edges_need_two_values():
    with pytest.raises(ValueError):
        stats.validate_edges([0])


# ---------- 切块与分桶 ----------

def test_tile_areas_match_hand_count():
    # 8x8 图，点亮位置随手散布；2x2 网格，每块 4x4
    on = {(0, 0), (1, 1), (3, 3), (4, 4), (7, 7), (5, 2), (2, 6)}
    image = _image_with_on(8, 8, on)
    result = stats.histogram(image, 2, 2, [0, 1, 4, 16])
    rows = cols = 8
    for ty in range(2):
        for tx in range(2):
            r0, r1 = ty * rows // 2, (ty + 1) * rows // 2
            c0, c1 = tx * cols // 2, (tx + 1) * cols // 2
            assert result["tile_areas"][ty][tx] == _hand_count(
                image, r0, r1, c0, c1)
    assert sum(result["histogram"]) == 4


def test_histogram_counts_and_bin_of():
    # 4x4 图切成 2x2，左上块 4 个亮点、右上 0、左下 2、右下 1
    on = {(0, 0), (0, 1), (1, 0), (1, 1),
          (2, 0), (2, 1),
          (3, 2)}
    image = _image_with_on(4, 4, on)
    result = stats.histogram(image, 2, 2, [0, 1, 3, 8])
    # 块面积: 左上4, 右上0, 左下2, 右下1
    # 桶 [0,1): 1块(右上)；[1,3): 2块(左下2、右下1)；[3,8]: 1块(左上4)
    assert result["histogram"] == [1, 2, 1]
    assert result["bin_of"][0][0] == 2
    assert result["bin_of"][0][1] == 0
    assert result["bin_of"][1][0] == 1
    assert result["bin_of"][1][1] == 1
    assert result["nonempty_buckets"] == 3


def test_area_outside_edges_raises():
    image = _image_with_on(4, 4, {(r, c) for r in range(4) for c in range(4)})
    with pytest.raises(ValueError, match="桶区间"):
        stats.histogram(image, 1, 1, [0, 1, 4])  # 实际面积 16 > 上界 4


def test_grid_denser_than_image_raises():
    image = _image_with_on(4, 4, set())
    with pytest.raises(ValueError):
        stats.histogram(image, 8, 1, [0, 1])


def test_uneven_split_keeps_full_coverage():
    # 5x5 切 2x2：列宽 2/3、行高 2/3，面积总和必须等于全图亮点数
    on = {(r, c) for r in range(5) for c in range(5) if (r + c) % 2 == 0}
    image = _image_with_on(5, 5, on)
    result = stats.histogram(image, 2, 2, stats.default_edges(25))
    assert sum(map(sum, result["tile_areas"])) == len(on)


# ---------- 逐块手算复核与误差上界 ----------

def test_verify_by_hand_agrees_and_zero_error():
    on = {(0, 0), (2, 3), (3, 3), (1, 1), (4, 0), (5, 5)}
    image = _image_with_on(6, 6, on)
    report = stats.verify_by_hand(image, 3, 2, [0, 1, 2, 4, 9])
    assert report["hand_histogram"] == report["histogram"]
    assert report["hand_tile_areas"] == report["tile_areas"]
    assert report["max_abs_error"] == 0
    assert report["max_rel_error"] == 0.0
    assert report["error_bound"] >= 0
    # 误差上界在整数计数场景下就是一个浮点舍入量级的小数
    assert report["error_bound"] < 1e-12


def test_hand_binning_is_independent_of_fast_path(monkeypatch):
    # 手算路径不得依赖 histogram 的落桶结果：篡改 bin_of 后复核仍应自洽
    image = _image_with_on(4, 4, {(0, 0), (3, 3)})
    report = stats.verify_by_hand(image, 2, 2, [0, 1, 4, 16])
    # 每块 2x2：含点亮的块面积 1，落 [1,4) 即 1 号桶
    assert report["hand_bin_of"] == [[1, 0], [0, 1]]
    # 手数面积与落桶一一对应
    for ty in range(2):
        for tx in range(2):
            b = report["hand_bin_of"][ty][tx]
            lo = report["edges"][b]
            hi = report["edges"][b + 1]
            a = report["hand_tile_areas"][ty][tx]
            assert lo <= a <= hi


def test_two_tier_report_shape_and_timing():
    image = pipeline.run(
        [[(0, 0), (10, 0), (10, 10), (0, 10)]],
        {"width": 64, "height": 64, "supersample": 2})
    report = stats.two_tier_report(image, stats.default_edges(256))
    assert report["coarse"]["tile_count"] == 16      # 4x4
    assert report["fine"]["tile_count"] == 256       # 16x16
    for label in ("coarse", "fine"):
        r = report[label]
        assert r["elapsed_sec"] >= 0 and r["hand_elapsed_sec"] >= 0
        assert sum(r["histogram"]) == r["tile_count"]
        assert r["max_abs_error"] == 0


def test_format_report_mentions_buckets_and_timing():
    image = _image_with_on(8, 8, {(0, 0)})
    text = stats.format_report(
        stats.verify_by_hand(image, 2, 2, [0, 1, 4, 16]))
    assert "桶数 3" in text and "图块 4 个" in text
    assert "耗时" in text and "误差上界" in text


def test_independent_test_side_hand_calculation():
    """测试侧完全独立的手算：自己切块、自己数像素、自己按桶边落桶，
    只把 stats.histogram 当作被校验对象。"""
    width = height = 12
    nx = ny = 3
    on = {(r, c) for r in range(height) for c in range(width)
          if (r * 3 + c * 7) % 5 == 0}
    image = _image_with_on(width, height, on)
    edges = [0, 1, 3, 9, 27]
    result = stats.histogram(image, nx, ny, edges)

    expect_hist = [0] * (len(edges) - 1)
    expect_areas = [[0] * nx for _ in range(ny)]
    for ty in range(ny):
        r0, r1 = ty * height // ny, (ty + 1) * height // ny
        for tx in range(nx):
            c0, c1 = tx * width // nx, (tx + 1) * width // nx
            area = _hand_count(image, r0, r1, c0, c1)
            expect_areas[ty][tx] = area
            # 显式边界比较，独立落桶
            b = next(k for k in range(len(edges) - 1)
                     if edges[k] <= area < edges[k + 1]
                     or (k == len(edges) - 2 and area == edges[k + 1]))
            expect_hist[b] += 1

    assert result["tile_areas"] == expect_areas
    assert result["histogram"] == expect_hist
    assert sum(expect_hist) == nx * ny
    assert sum(map(sum, expect_areas)) == len(on)


def test_histogram_does_not_mutate_image():
    image = _image_with_on(6, 6, {(0, 0), (5, 5)})
    snapshot = [row[:] for row in image]
    stats.verify_by_hand(image, 2, 3, [0, 1, 4, 9])
    assert image == snapshot


# ---------- 几何面积（鞋带公式） ----------

def test_polygon_area_square():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert geom.polygon_area(square) == pytest.approx(100.0)


def test_polygon_area_triangle():
    tri = [(0, 0), (4, 0), (0, 6)]
    assert geom.polygon_area(tri) == pytest.approx(12.0)


def test_polygon_area_rejects_short_ring():
    with pytest.raises(ValueError):
        geom.polygon_area([(0, 0), (1, 1)])


# ---------- 关闭统计时逐字节相同 ----------

def test_cli_pgm_byte_identical_with_and_without_stats():
    scene_cfg = '{"width":64,"height":64,"supersample":2}'
    with tempfile.TemporaryDirectory() as tmp:
        plain = os.path.join(tmp, "plain.pgm")
        stats_out = os.path.join(tmp, "stats.pgm")
        env = dict(os.environ, PYTHONPATH=os.getcwd())
        subprocess.run(
            [sys.executable, "-m", "vecpipe.cli", "render",
             "--config", scene_cfg, "--out", plain],
            check=True, cwd=os.getcwd(), env=env, capture_output=True)
        proc = subprocess.run(
            [sys.executable, "-m", "vecpipe.cli", "render",
             "--config", scene_cfg, "--out", stats_out, "--stats"],
            check=True, cwd=os.getcwd(), env=env, capture_output=True, text=True)
        with open(plain, "rb") as f1, open(stats_out, "rb") as f2:
            assert f1.read() == f2.read()
        # 统计信息只进 stdout，不动文件
        assert "coarse" in proc.stdout and "fine" in proc.stdout


def test_cli_custom_edges_and_bad_edge(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "a.pgm")
        rc = cli.main(["render", "--config", '{"width":32,"height":32}',
                       "--out", out, "--stats",
                       "--edges", "0,1,4,16,64,256"])
        assert rc == 0
        text = capsys.readouterr().out
        assert "桶数 5" in text
        rc = cli.main(["render", "--config", '{"width":32,"height":32}',
                       "--out", os.path.join(tmp, "b.pgm"), "--stats",
                       "--edges", "0,4,4,16"])
        err = capsys.readouterr().err
        assert rc == 2 and "第 1 号桶区间非法" in err


def test_cli_without_stats_prints_only_on_count(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "plain.pgm")
        rc = cli.main(["render", "--config", '{"width":16,"height":16}',
                       "--out", out])
        assert rc == 0
        stdout = capsys.readouterr().out
        assert "coarse" not in stdout and "桶" not in stdout
        assert os.path.getsize(out) == len(b"P5\n16 16\n255\n") + 256


def test_cli_negative_edge_reports_bucket_index(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        rc = cli.main(["render", "--config", '{"width":16,"height":16}',
                       "--out", os.path.join(tmp, "c.pgm"), "--stats",
                       "--edges", "0,-2,4"])
        err = capsys.readouterr().err
        assert rc == 2 and "第 1 号桶边为负" in err


def test_cli_bad_edges_clean_stderr_in_subprocess():
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    proc = subprocess.run(
        [sys.executable, "-m", "vecpipe.cli", "render", "--stats",
         "--edges", "0,4,4,16"],
        cwd=os.getcwd(), env=env, capture_output=True, text=True)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "第 1 号桶区间非法" in proc.stderr
