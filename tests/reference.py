"""独立参考实现：逐像素手算的感知空间渐变与 CIEDE2000 色差。

本模块刻意不 import vecpipe.shading，所有数学独立重写，
用于与生产路径（LUT 查表）对照，给出色差上界。
"""
import math


# ---------------- sRGB 传递函数（独立实现，对照生产代码用）
def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * c ** (1.0 / 2.4) - 0.055


def reference_value(stops, t):
    """逐像素手算参考值：不做任何量化/查表，返回 sRGB 0..255 float 元组。

    stops 与 GradientRamp 同构。单色标退化为纯色。
    步骤：色标转线性光 -> 手算 Fritsch-Carlson 切线 ->
    Hermite 三次插值 -> 转回 sRGB。
    """
    positions = [p for p, _ in stops]
    raw_cols = [list(c) if isinstance(c, (tuple, list)) else [c]
                for _, c in stops]
    n = len(stops)
    channels = len(raw_cols[0])

    if n == 1:
        out = [linear_to_srgb(srgb_to_linear(v / 255.0)) * 255.0
               for v in raw_cols[0]]
        return tuple(out)

    if t <= positions[0]:
        k, u, h = 0, 0.0, positions[1] - positions[0]
    elif t >= positions[-1]:
        k, h = n - 2, positions[-1] - positions[-2]
        u = 1.0
    else:
        k = 0
        while positions[k + 1] < t:
            k += 1
        if t <= positions[k + 1]:
            pass
        h = positions[k + 1] - positions[k]
        u = (t - positions[k]) / h

    result = []
    for ch in range(channels):
        ys = [srgb_to_linear(row[ch] / 255.0) for row in raw_cols]
        hs = [positions[i + 1] - positions[i] for i in range(n - 1)]
        delta = [(ys[i + 1] - ys[i]) / hs[i] for i in range(n - 1)]

        # Fritsch-Carlson 切线（独立重写）。
        m = [0.0] * n
        m[0], m[-1] = delta[0], delta[-1]
        for j in range(1, n - 1):
            d0, d1 = delta[j - 1], delta[j]
            if d0 == 0.0 or d1 == 0.0 or d0 * d1 <= 0.0:
                m[j] = 0.0
            else:
                w1 = 2.0 * hs[j] + hs[j - 1]
                w2 = hs[j] + 2.0 * hs[j - 1]
                m[j] = (w1 * d0 + w2 * d1) / (w1 + w2)
        for j in range(n - 1):
            d = delta[j]
            if d == 0.0:
                m[j] = m[j + 1] = 0.0
                continue
            a, b = m[j] / d, m[j + 1] / d
            s = a * a + b * b
            if s > 9.0:
                tau = 3.0 / math.sqrt(s)
                m[j] = tau * a * d
                m[j + 1] = tau * b * d

        t2, t3 = u * u, u * u * u
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + u
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        lin = (h00 * ys[k] + h10 * h * m[k]
               + h01 * ys[k + 1] + h11 * h * m[k + 1])
        result.append(linear_to_srgb(lin) * 255.0)
    return tuple(result)


# ---------------- sRGB -> Lab 与 CIEDE2000（Sharma 等 2005 修订版）
def srgb255_to_lab(rgb):
    """sRGB 0..255 三元组 -> CIE Lab（D65）。"""
    vals = [srgb_to_linear(max(0.0, min(255.0, v)) / 255.0) for v in rgb]
    # IEC 61966-2-1 sRGB -> XYZ (D65)。
    r, g, b = vals
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    # D65 白点。
    xn, yn, zn = 0.95047, 1.0, 1.08883
    t = 0.008856

    def f(v):
        return v ** (1.0 / 3.0) if v > t ** 3 else 7.787 * v + 16.0 / 116.0

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def ciede2000(lab1, lab2, kL=1.0, kC=1.0, kH=1.0):
    """两 Lab 颜色的 CIEDE2000 色差 ΔE00。"""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    G = 0.5 * (1.0 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7)))
    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)

    def hue(a, b):
        if a == 0.0 and b == 0.0:
            return 0.0
        h = math.degrees(math.atan2(b, a))
        return h + 360.0 if h < 0.0 else h

    h1p = hue(a1p, b1)
    h2p = hue(a2p, b2)
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0.0:
        dhp = 0.0
    elif h2p - h1p > 180.0:
        dhp = h2p - h1p - 360.0
    elif h2p - h1p < -180.0:
        dhp = h2p - h1p + 360.0
    else:
        dhp = h2p - h1p
    dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))
    Lbp = (L1 + L2) / 2.0
    Cbp = (C1p + C2p) / 2.0
    if C1p * C2p == 0.0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) > 180.0:
        hbp = (h1p + h2p + 360.0) / 2.0
    else:
        hbp = (h1p + h2p) / 2.0
    T = (1.0 - 0.17 * math.cos(math.radians(hbp - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hbp))
         + 0.32 * math.cos(math.radians(3.0 * hbp + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hbp - 63.0)))
    dtheta = 30.0 * math.exp(-(((hbp - 275.0) / 25.0) ** 2))
    RC = 2.0 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    SL = 1.0 + (0.015 * (Lbp - 50.0) ** 2) / math.sqrt(
        20.0 + (Lbp - 50.0) ** 2)
    SC = 1.0 + 0.045 * Cbp
    SH = 1.0 + 0.015 * Cbp * T
    RT = -math.sin(math.radians(2.0 * dtheta)) * RC
    term = ((dLp / (kL * SL)) ** 2
            + (dCp / (kC * SC)) ** 2
            + (dHp / (kH * SH)) ** 2
            + RT * (dCp / (kC * SC)) * (dHp / (kH * SH)))
    return math.sqrt(term)


def max_color_diff(stops, lut_values, samples=4096, shadow_floor=2.0):
    """对 [0,1] 密集采样，比较 LUT 量化值与逐像素手算精确值。

    返回 (max_dE, max_level, body_dE, body_level)：
    max_* 为全区间上界；body_* 排除参考值各通道低于 shadow_floor 码值的
    近黑样本——那里 8bit sRGB 相邻码值本身就有约 4.5 ΔE00 的固有间距，
    属于输出格式的量化下限而非 ramp/LUT 误差。
    """
    max_e = max_g = 0.0
    body_e = body_g = 0.0
    # 通道数以色标定义为准（生产路径灰度返回 int、RGB 返回 tuple，
    # 不能用返回值形态判定）。
    channels = len(stops[0][1]) if isinstance(
        stops[0][1], (tuple, list)) else 1
    for i in range(samples + 1):
        t = i / samples
        ref = reference_value(stops, t)
        got = lut_values(t)
        got = got if isinstance(got, tuple) else (got,)
        if channels == 1:
            got = (got[0], got[0], got[0])
            ref = (ref[0], ref[0], ref[0])
        e = ciede2000(srgb255_to_lab(got), srgb255_to_lab(ref))
        g = max(abs(a - b) for a, b in zip(got, ref))
        max_e = max(max_e, e)
        max_g = max(max_g, g)
        if min(ref) >= shadow_floor:
            body_e = max(body_e, e)
            body_g = max(body_g, g)
    return max_e, max_g, body_e, body_g
