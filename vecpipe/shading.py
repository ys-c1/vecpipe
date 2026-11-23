"""着色：平面色与线性渐变，以及感知空间的多色标单调三次渐变。

渐变 ramp 的管线（见 GradientRamp）：
sRGB 色标 --srgb_to_linear--> 线性光 --Fritsch-Carlson 单调三次切线+
Hermite 插值--> 线性光 --linear_to_srgb--> sRGB 8bit。
在线性光空间插值避免了直接在 gamma 编码值上线性插值造成的暗部发灰。
"""
import bisect
import math

from .config import ConfigError


# ---------------------------------------------------------------- 原有接口
# 以下三个函数保持原样，输出逐字节不变。

def flat(intensity):
    if not 0.0 <= intensity <= 1.0:
        raise ConfigError("intensity 超出范围")
    return int(255 * intensity)


def gradient(t):
    if not 0.0 <= t <= 1.0:
        raise ConfigError("t 超出范围")
    return int(255 * t)


def apply(image, mode="flat", top=1.0, bottom=0.0):
    if mode not in ("flat", "gradient"):
        raise ConfigError("未知着色模式")
    height = len(image)
    for row in range(height):
        if mode == "flat":
            value = flat(top)
        else:
            t = top + (bottom - top) * (row / max(1, height - 1))
            value = gradient(t)
        for col in range(len(image[0])):
            if image[row][col]:
                image[row][col] = value
    return image


# ------------------------------------------------ sRGB 传递函数（线性光空间）
# 依据 IEC 61966-2-1（sRGB 标准），入参/出参均为 [0, 1]。

def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * c ** (1.0 / 2.4) - 0.055


# ------------------------------------------------ Fritsch-Carlson 单调切线
def monotone_tangents(xs, ys):
    """求单调分段三次 Hermite 插值在各节点的切线。

    依据 Fritsch & Carlson (1980), "Monotone Piecewise Cubic Interpolation",
    SIAM J. Numer. Anal. 17(2), 238-246：

    1. 区间割线 d_k = (y_{k+1}-y_k)/(x_{k+1}-x_k)。
    2. 端点切线取本侧单侧差分（自然边界，只依赖本侧数据）。
    3. 内点取相邻割线的加权调和式平均：
           w1 = 2*h_k + h_{k-1},  w2 = h_k + 2*h_{k-1}
           m_k = (w1*d_{k-1} + w2*d_k) / (w1 + w2)
       等间距时 w1=w2，退化为相邻割线的算术平均。
       相邻割线变号（数据本身出现极值）或其一为零时 m_k=0，
       保证不制造数据点之外的新极值。
    4. 单调充分条件：每个区间上 alpha=m_k/d_k、beta=m_{k+1}/d_k 落在
       alpha^2 + beta^2 <= 9 的椭圆内；越界则按 tau=3/sqrt(alpha^2+beta^2)
       同时缩放两端切线。缩放后 Hermite 基函数在该区间导数不变号，
       因而区间单调、无过冲/欠冲。

    要求 xs 严格递增且 xs、ys 均为有限实数（由调用方校验）。
    若计算出非有限切线，抛 ConfigError 并指出色标号。
    """
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]

    m = [0.0] * n
    m[0] = delta[0]
    m[-1] = delta[-1]
    for k in range(1, n - 1):
        d0, d1 = delta[k - 1], delta[k]
        if d0 == 0.0 or d1 == 0.0 or d0 * d1 <= 0.0:
            m[k] = 0.0
        else:
            w1 = 2.0 * h[k] + h[k - 1]
            w2 = h[k] + 2.0 * h[k - 1]
            m[k] = (w1 * d0 + w2 * d1) / (w1 + w2)

    for k in range(n - 1):
        d = delta[k]
        if d == 0.0:
            m[k] = 0.0
            m[k + 1] = 0.0
            continue
        alpha = m[k] / d
        beta = m[k + 1] / d
        s = alpha * alpha + beta * beta
        if s > 9.0:
            tau = 3.0 / math.sqrt(s)
            m[k] = tau * alpha * d
            m[k + 1] = tau * beta * d

    for i, v in enumerate(m):
        if not math.isfinite(v):
            raise ConfigError("切线发散：色标 %d 的切线不是有限值" % i)
    return m


def _hermite(y0, y1, m0, m1, h, t):
    """区间 [0, h] 上的三次 Hermite 求值，t 为区间内局部参数 [0, 1]。"""
    t2 = t * t
    t3 = t2 * t
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    return h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1


def _quantize(value):
    """sRGB [0,1] -> 8bit 整数，含夹取。"""
    q = int(math.floor(value * 255.0 + 0.5))
    if q < 0:
        return 0
    if q > 255:
        return 255
    return q


def _as_color(color, index):
    if isinstance(color, bool) or not isinstance(color, (int, float)):
        if not isinstance(color, (list, tuple)):
            raise ConfigError("色标 %d 的颜色必须是 0..255 数值或其元组" % index)
        cols = list(color)
    else:
        cols = [color]
    if not cols:
        raise ConfigError("色标 %d 的颜色不能为空" % index)
    out = []
    for v in cols:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError("色标 %d 的颜色通道必须是数值" % index)
        if not math.isfinite(v):
            # 非有限值进入割线/切线必产生 inf/NaN，即切线发散。
            raise ConfigError("切线发散：色标 %d 的颜色不是有限值" % index)
        if v < 0.0 or v > 255.0:
            raise ConfigError("色标 %d 的颜色超出 [0, 255]" % index)
        out.append(float(v))
    return out


class GradientRamp:
    """多色标感知空间渐变。

    stops: [(position, color), ...]，position 为 [0,1] 且严格递增；
    color 为 0..255 的 sRGB 数值（灰度）或 (r, g, b) 元组，各色标通道数
    必须一致。色标号从 0 开始，所有报错均指出具体色标号。

    插值在线性光空间按 Fritsch-Carlson 单调三次 Hermite 完成（见
    monotone_tangents），再编码回 sRGB。lut_size 为预计算查表大小
    （默认 8192：配合 floor 索引 + 格点间线性插值，即便色标极端不等距
    也能把 ramp 自身的量化误差压到 1 个 sRGB 级 / ΔE00<1 以内；约 64KB，
    一次性建表），生产路径逐像素 O(1) 查表；at() 提供不量化的精确求值。
    注意近黑端相邻 8bit 码值本身就有约 4.5 ΔE00 的固有间距，这是 sRGB
    8bit 输出格式的量化下限，与 LUT 精度无关。
    单色标退化为纯色。
    """

    def __init__(self, stops, lut_size=8192):
        if not isinstance(stops, (list, tuple)) or len(stops) < 1:
            raise ConfigError("色标至少需要一个")
        if not isinstance(lut_size, int) or lut_size < 2:
            raise ConfigError("lut_size 必须是 >=2 的整数")

        norm = []
        channels = None
        prev_x = None
        for i, stop in enumerate(stops):
            if not isinstance(stop, (list, tuple)) or len(stop) != 2:
                raise ConfigError("色标 %d 格式应为 (位置, 颜色)" % i)
            x, color = stop
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise ConfigError("色标 %d 的位置必须是数值" % i)
            if not math.isfinite(x):
                raise ConfigError("色标 %d 的位置必须有限" % i)
            if x < 0.0 or x > 1.0:
                raise ConfigError("色标 %d 的位置超出 [0, 1]" % i)
            if prev_x is not None and x <= prev_x:
                raise ConfigError(
                    "色标 %d 位置不单调：位置必须严格递增（色标号从 0 开始）" % i)
            cols = _as_color(color, i)
            if channels is None:
                channels = len(cols)
            elif len(cols) != channels:
                raise ConfigError("色标 %d 的通道数与前面色标不一致" % i)
            norm.append((float(x), cols))
            prev_x = x

        self.stops = norm
        self.n_stops = len(norm)
        self.channels = channels
        self.lut_size = lut_size
        self._positions = [p for p, _ in norm]
        # 转到线性光。
        self._linear = [[srgb_to_linear(v / 255.0) for v in cols]
                        for _, cols in norm]
        # 按通道转置，避免建表时每次求值都重建列。
        self._channel_ys = [
            [row[ch] for row in self._linear] for ch in range(channels)]

        if self.n_stops == 1:
            self._tangents = None
            solid_enc = [linear_to_srgb(c) for c in self._linear[0]]
            self._solid = tuple(_quantize(c) for c in solid_enc)
        else:
            self._tangents = [
                monotone_tangents(self._positions, ys)
                for ys in self._channel_ys]
            self._solid = None

        self._lut = [self._eval_encoded(j / (lut_size - 1))
                     for j in range(lut_size)]

    # ------------------------------------------------------------ 求值
    def _segment(self, t):
        """返回 t 所在区间号 k（夹取到首尾区间）。"""
        if t <= self._positions[0]:
            return 0
        if t >= self._positions[-1]:
            return self.n_stops - 2
        return bisect.bisect_right(self._positions, t) - 1

    def at(self, t):
        """精确求值（未量化），返回 sRGB 0..255 的 float 或 float 元组。"""
        if not 0.0 <= t <= 1.0:
            raise ConfigError("t 超出 [0, 1]")
        if self._solid is not None:
            return self._solid[0] if self.channels == 1 else self._solid
        return self._eval_encoded(t, quantize=False)

    def _eval_encoded(self, t, quantize=True):
        if self._solid is not None:
            if not quantize:
                return (float(self._solid[0]) if self.channels == 1
                        else tuple(float(v) for v in self._solid))
            return self._solid[0] if self.channels == 1 else self._solid
        k = self._segment(t)
        x0 = self._positions[k]
        h = self._positions[k + 1] - x0
        u = 0.0 if h == 0.0 else (t - x0) / h
        out = []
        for ch in range(self.channels):
            ys = self._channel_ys[ch]
            m = self._tangents[ch]
            # m 的单位是 dy/dx；Hermite 基以局部参数 u∈[0,1] 为自变量，
            # 故切线项须乘区间宽 h（m*h 才是对 u 的导数）。
            lin = _hermite(ys[k], ys[k + 1], m[k], m[k + 1], h, u)
            # enc 已在 sRGB 0..255 尺度，最近邻取整并夹取（线性光单调
            # 插值理论上不会越界，夹取仅为防御浮点误差）。
            enc = linear_to_srgb(lin) * 255.0
            if quantize:
                q = int(math.floor(enc + 0.5))
                enc = 0 if q < 0 else 255 if q > 255 else q
            out.append(enc)
        if self.channels == 1:
            return out[0]
        return tuple(out)

    def lookup(self, t):
        """生产路径：O(1) 查表，返回量化后的 sRGB 值。

        采用 floor 索引 + 格点间线性插值：把量化误差限制在单个 LUT
        格的编码值差之内，避免最近邻索引在陡峭段跨越多个 sRGB 级。
        """
        if not 0.0 <= t <= 1.0:
            raise ConfigError("t 超出 [0, 1]")
        pos = t * (self.lut_size - 1)
        idx = int(math.floor(pos))
        if idx < 0:
            idx = 0
        if idx >= self.lut_size - 1:
            return self._lut[self.lut_size - 1]
        frac = pos - idx
        v0 = self._lut[idx]
        v1 = self._lut[idx + 1]
        if self.channels == 1:
            return int(math.floor(v0 + (v1 - v0) * frac + 0.5))
        return tuple(int(math.floor(a + (b - a) * frac + 0.5))
                     for a, b in zip(v0, v1))

    def apply(self, image):
        """按行施加纵向渐变（顶行 t=0、底行 t=1）；只改写非零像素。"""
        height = len(image)
        if height == 0:
            return image
        width = len(image[0])
        denom = max(1, height - 1)
        for row in range(height):
            value = self.lookup(row / denom)
            for col in range(width):
                if image[row][col]:
                    image[row][col] = value
        return image


def apply_ramp(image, stops, lut_size=8192):
    """便捷入口：用多色标 ramp 着色 image（原地修改并返回）。"""
    return GradientRamp(stops, lut_size=lut_size).apply(image)
