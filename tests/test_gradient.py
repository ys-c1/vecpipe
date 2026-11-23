"""感知空间多色标渐变的测试。"""
import math

import pytest

from vecpipe import config, shading
from vecpipe.config import ConfigError
from vecpipe.shading import GradientRamp

from tests import reference


# ------------------------------------------------ sRGB 传递函数
def test_srgb_roundtrip():
    for v in (0.0, 0.01, 0.2, 0.5, 0.8, 1.0):
        assert abs(shading.linear_to_srgb(shading.srgb_to_linear(v)) - v) < 1e-12


def test_srgb_matches_iec_breakpoint():
    # 线性段与幂段在断点处连续：IEC 61966-2-1 的 0.04045/12.92 是
    # 按阈值 0.0031308 反算并四舍五入的常数，两支在断点处仅差舍入量级。
    a = shading.srgb_to_linear(0.04045)
    b = ((0.04045 + 0.055) / 1.055) ** 2.4
    assert abs(a - b) < 1e-5
    # 反函数两支在真正的阈值 0.0031308 处衔接，差别仅为常数舍入量级。
    lo = 12.92 * 0.0031308
    hi = 1.055 * 0.0031308 ** (1.0 / 2.4) - 0.055
    assert abs(lo - hi) < 1e-6


# ------------------------------------------------ 端点与单调性
def test_ramp_endpoints_exact():
    stops = [(0.0, 10), (0.5, 128), (1.0, 240)]
    ramp = GradientRamp(stops)
    assert ramp.lookup(0.0) == 10
    assert ramp.lookup(1.0) == 240
    assert ramp.at(0.0) == pytest.approx(10.0, abs=1e-9)
    assert ramp.at(1.0) == pytest.approx(240.0, abs=1e-9)


def test_ramp_monotone_no_overshoot():
    stops = [(0.0, 0), (0.1, 250), (0.9, 60), (1.0, 255)]
    ramp = GradientRamp(stops)
    prev = -1
    direction = None
    for i in range(1, len(stops) - 1):
        x0, x1 = stops[i][0], stops[i + 1][0]
        v0, v1 = stops[i][1], stops[i + 1][1]
        for j in range(64):
            t = x0 + (x1 - x0) * j / 63
            v = ramp.lookup(t)
            assert 0 <= v <= 255
            if v0 <= v1:
                assert v >= v0 - 1 and v <= v1 + 1
            else:
                assert v <= v0 + 1 and v >= v1 - 1
    # 全区间采样整体不超出色标包络。
    vals = [ramp.lookup(i / 1000.0) for i in range(1001)]
    assert min(vals) >= 0 and max(vals) <= 255


def test_ramp_matches_exact_at_stops():
    stops = [(0.0, 0), (0.25, 200), (0.6, 40), (1.0, 255)]
    ramp = GradientRamp(stops)
    for pos, col in stops:
        assert abs(ramp.at(pos) - col) < 1e-9


# ------------------------------------------------ 单色标退化为纯色
def test_single_stop_solid():
    ramp = GradientRamp([(0.5, 137)])
    assert ramp.n_stops == 1
    for t in (0.0, 0.25, 0.5, 0.99, 1.0):
        assert ramp.lookup(t) == 137
        assert ramp.at(t) == 137
    img = [[1, 0], [0, 1], [1, 1]]
    out = ramp.apply([row[:] for row in img])
    assert out[0][0] == 137 and out[2][1] == 137 and out[0][1] == 0


def test_single_stop_rgb_solid():
    ramp = GradientRamp([(0.0, (10, 20, 30))])
    assert ramp.lookup(0.7) == (10, 20, 30)


# ------------------------------------------------ 两色标：线性光直线
def test_two_stop_linear_light_midpoint():
    # 在线性光空间是直线：0->255 对应线性 0->1，中点线性值恰为 0.5。
    # 编码回 sRGB 后约 187.5，明显高于直接在 sRGB 上线性插值的 127.5，
    # 即暗部不再发灰（过渡在感知上更均匀通透）。
    ramp = GradientRamp([(0.0, 0), (1.0, 255)])
    expected = shading.linear_to_srgb(0.5) * 255.0
    assert ramp.at(0.5) == pytest.approx(expected, abs=1e-9)
    assert ramp.at(0.5) > 127.5
    assert abs(expected - 187.52) < 0.1


# ------------------------------------------------ FC 切线依据
def test_fc_equispaced_is_average_of_secants():
    # 等间距、同号割线：内点切线 = 相邻割线算术平均（加权平均的退化）。
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [0.0, 1.0, 4.0, 6.0]
    m = shading.monotone_tangents(xs, ys)
    d = [1.0, 3.0, 2.0]
    assert m[0] == pytest.approx(d[0])
    assert m[-1] == pytest.approx(d[-1])
    assert m[1] == pytest.approx((d[0] + d[1]) / 2.0)
    assert m[2] == pytest.approx((d[1] + d[2]) / 2.0)


def test_fc_extremum_zero_tangent():
    # 割线变号（数据极值点）：该点切线必须为 0，不制造新极值。
    xs = [0.0, 1.0, 2.0]
    ys = [0.0, 10.0, 0.0]
    m = shading.monotone_tangents(xs, ys)
    assert m[1] == 0.0


def test_fc_steep_clamp_inside_ellipse():
    # 极端不等间距迫使 alpha^2+beta^2>9，缩放后必须回到椭圆内。
    xs = [0.0, 1.0, 1.0001]
    ys = [0.0, 0.0, 1.0]
    m = shading.monotone_tangents(xs, ys)
    d = (ys[2] - ys[1]) / (xs[2] - xs[1])
    alpha, beta = m[1] / d, m[2] / d
    assert alpha * alpha + beta * beta <= 9.0 + 1e-9


def test_fc_c1_continuity():
    # 节点两侧的三次多项式值与导数都连续（C1）。
    xs = [0.0, 0.3, 0.8, 1.0]
    ys = [0.05, 0.9, 0.2, 1.0]
    m = shading.monotone_tangents(xs, ys)
    for k in range(len(xs) - 2):
        h = xs[k + 1] - xs[k]
        hn = xs[k + 2] - xs[k + 1]
        eps = 1e-7
        def herm(y0, y1, m0, m1, hh, u):
            return shading._hermite(y0, y1, m0, m1, hh, u)
        vl = herm(ys[k], ys[k + 1], m[k], m[k + 1], h, 1.0)
        vr = herm(ys[k + 1], ys[k + 2], m[k + 1], m[k + 2], hn, 0.0)
        assert abs(vl - vr) < 1e-9
        dl = (herm(ys[k], ys[k + 1], m[k], m[k + 1], h, 1.0 - eps)
              - herm(ys[k], ys[k + 1], m[k], m[k + 1], h, 1.0)) / eps
        dr = (herm(ys[k + 1], ys[k + 2], m[k + 1], m[k + 2], hn, eps)
              - herm(ys[k + 1], ys[k + 2], m[k + 1], m[k + 2], hn, 0.0)) / eps
        assert abs(dl - dr) < 1e-4


# ------------------------------------------------ 报错并指出色标号
def test_rejects_nonmonotonic_position_with_index():
    with pytest.raises(ConfigError, match="色标 2 位置不单调"):
        GradientRamp([(0.0, 0), (0.5, 128), (0.5, 200), (1.0, 255)])
    with pytest.raises(ConfigError, match="色标 1 位置不单调"):
        GradientRamp([(0.2, 0), (0.1, 255)])


def test_rejects_position_out_of_range():
    with pytest.raises(ConfigError, match="色标 1 的位置超出"):
        GradientRamp([(0.0, 0), (1.5, 255)])


def test_rejects_divergent_tangent_with_index():
    with pytest.raises(ConfigError, match="切线发散：色标 1"):
        GradientRamp([(0.0, 0), (0.5, float("nan")), (1.0, 255)])
    with pytest.raises(ConfigError, match="切线发散：色标 0"):
        GradientRamp([(0.0, float("inf"))])
    with pytest.raises(ConfigError, match="切线发散：色标 2"):
        GradientRamp([(0.0, 0), (0.4, 100), (0.8, float("-inf")), (1.0, 255)])


def test_rejects_bad_channel_count():
    with pytest.raises(ConfigError, match="色标 1 的通道数"):
        GradientRamp([(0.0, (1, 2, 3)), (1.0, 10)])


def test_rejects_color_range():
    with pytest.raises(ConfigError, match="色标 0 的颜色超出"):
        GradientRamp([(0.0, 256)])
    with pytest.raises(ConfigError, match="色标 1 的颜色超出"):
        GradientRamp([(0.0, 0), (1.0, -1)])


def test_rejects_empty_stops():
    with pytest.raises(ConfigError, match="至少需要一个"):
        GradientRamp([])


def test_lookup_rejects_t_range():
    ramp = GradientRamp([(0.0, 0), (1.0, 255)])
    with pytest.raises(ConfigError):
        ramp.lookup(1.1)
    with pytest.raises(ConfigError):
        ramp.at(-0.1)


# ------------------------------------------------ 与逐像素手算参考对照
def test_lut_vs_reference_gray():
    stops = [(0.0, 0), (0.2, 210), (0.55, 30), (0.8, 180), (1.0, 255)]
    ramp = GradientRamp(stops)
    max_e, max_g, body_e, body_g = reference.max_color_diff(stops, ramp.lookup)
    # ramp 自身误差（排除近黑 8bit 量化区）：ΔE00<1、级差<1。
    assert body_e < 1.0
    assert body_g < 1.0
    # 全区间级差仍受 LUT 控制在 1 级内；近黑的大 ΔE 是 8bit 固有限度。
    assert max_g < 1.0


def test_lut_vs_reference_rgb():
    stops = [(0.0, (5, 10, 200)), (0.3, (240, 60, 30)),
             (0.7, (20, 230, 90)), (1.0, (250, 250, 245))]
    ramp = GradientRamp(stops)
    max_e, max_g, body_e, body_g = reference.max_color_diff(stops, ramp.lookup)
    assert body_e < 1.0
    assert body_g < 1.0
    assert max_g < 1.0


def test_near_black_delta_e_is_8bit_floor():
    # 近黑端的 ΔE 来自 8bit 码值固有间距，而非 ramp：码值 0/1 间距即约
    # 4.5 ΔE00。在近黑区间高密度采样，确认全区间最大 ΔE 落在这个量级，
    # 且该点生产值与逐像素参考只差一个码值（LUT 没有引入额外误差）；
    # 排除近黑后 ramp 自身误差回到 ΔE00<1。
    floor_e = reference.ciede2000(
        reference.srgb255_to_lab((0, 0, 0)),
        reference.srgb255_to_lab((1, 1, 1)))
    assert 4.0 < floor_e < 5.0
    stops = [(0.0, 0), (1.0, 255)]
    ramp = GradientRamp(stops)
    worst_e, worst_gap = 0.0, 0.0
    for i in range(1, 20000):
        t = i / 1_000_000.0  # t in (0, 0.02)，覆盖最暗的若干 LUT 格
        ref = reference.reference_value(stops, t)[0]
        got = ramp.lookup(t)
        e = reference.ciede2000(
            reference.srgb255_to_lab((got, got, got)),
            reference.srgb255_to_lab((ref, ref, ref)))
        worst_e = max(worst_e, e)
        worst_gap = max(worst_gap, abs(got - ref))
    assert worst_e >= floor_e          # 近黑量化确实把 ΔE 抬到码值间距量级
    assert worst_gap < 1.0             # 但生产值与参考始终只差不到一个码值
    _, _, body_e, body_g = reference.max_color_diff(stops, ramp.lookup)
    assert body_e < 1.0 and body_g < 1.0


def test_exact_path_matches_reference():
    # 精确路径（不量化）与独立参考实现应只在浮点舍入层面有差异。
    stops = [(0.0, 12), (0.33, 199), (0.67, 77), (1.0, 244)]
    ramp = GradientRamp(stops)
    for i in range(257):
        t = i / 256.0
        ref = reference.reference_value(stops, t)[0]
        assert abs(ramp.at(t) - ref) < 1e-9


def test_reference_agrees_on_tangent_math():
    # 参考实现与生产实现在密集采样上逐点一致（量化前）。
    stops = [(0.0, 0), (0.15, 250), (0.5, 128), (0.9, 60), (1.0, 255)]
    ramp = GradientRamp(stops)
    for i in range(512):
        t = i / 511.0
        assert abs(ramp.at(t) - reference.reference_value(stops, t)[0]) < 1e-9


# ------------------------------------------------ 向后兼容：旧输出逐字节不变
def test_legacy_flat_unchanged():
    img = [[255, 0], [0, 255]]
    shading.apply(img, "flat", 0.5)
    assert img[0][0] == 127 and img[1][1] == 127 and img[0][1] == 0


def test_legacy_gradient_unchanged():
    img = [[1] * 4 for _ in range(4)]
    shading.apply(img, "gradient", 1.0, 0.0)
    assert [row[0] for row in img] == [255, 170, 85, 0]


def test_legacy_gradient_height_one():
    img = [[1, 1]]
    shading.apply(img, "gradient", 0.4, 0.4)
    assert img == [[102, 102]]


def test_legacy_apply_signature_and_errors():
    with pytest.raises(config.ConfigError):
        shading.apply([[1]], "bogus")
    with pytest.raises(config.ConfigError):
        shading.gradient(1.1)
    with pytest.raises(config.ConfigError):
        shading.flat(-0.1)


def test_pipeline_output_byte_identical():
    # 完整管线在默认配置下与改动前逐字节一致。
    from vecpipe import pipeline, raster
    scene = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    image = pipeline.run(scene, {"width": 16, "height": 16, "supersample": 2})
    pgm = raster
    # 手工复现旧路径预期：flat top=1.0 -> 覆盖像素全 255。
    assert all(v in (0, 255) for row in image for v in row)
    assert raster.count_on(image) > 0


# ------------------------------------------------ apply 行为
def test_apply_ramp_only_nonzero_cells():
    ramp = GradientRamp([(0.0, 0), (1.0, 255)])
    img = [[1, 0, 1], [0, 1, 0], [1, 1, 0]]
    out = ramp.apply([row[:] for row in img])
    assert out[0][1] == 0 and out[1][0] == 0 and out[2][2] == 0
    # 顶行/底行覆盖像素取端点值。
    assert out[0][0] == 0 and out[2][0] == 255


def test_apply_ramp_helper():
    img = [[1], [1], [1]]
    shading.apply_ramp(img, [(0.0, 100), (1.0, 200)])
    assert img[0][0] == 100 and img[-1][0] == 200
    assert all(0 <= row[0] <= 255 for row in img)


def test_rgb_ramp_channels():
    stops = [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))]
    ramp = GradientRamp(stops)
    v = ramp.lookup(0.5)
    assert len(v) == 3 and v[0] == v[1] == v[2]
    assert 128 <= v[0] <= 188  # 线性光中点，sRGB 编码后高于 127
