# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
make test
```

## 感知空间多色标渐变

`shading.GradientRamp(stops)` 支持任意色标数，全程在线性光空间插值：
sRGB 色标 → IEC 61966-2-1 转线性光 → Fritsch-Carlson 单调三次 Hermite
（依据 Fritsch & Carlson, 1980, SIAM J. Numer. Anal. 17(2)）→ 转回 sRGB，
避免直接在 gamma 编码值上线性插值造成的暗部发灰，并保证单调无过冲。

```python
from vecpipe.shading import GradientRamp
ramp = GradientRamp([(0.0, 0), (0.5, 128), (1.0, 255)])  # 灰度
ramp = GradientRamp([(0.0, (0, 0, 0)), (1.0, (255, 255, 255))])  # RGB
ramp.apply(image)          # 生产路径：O(1) LUT 查表
ramp.at(0.3)               # 精确求值（不量化）
```

位置必须严格递增，否则报 `ConfigError` 并指出色标号（从 0 开始）；
颜色非有限导致切线发散同样报错并指出色标号；单色标退化为纯色。
逐像素手算参考实现与 CIEDE2000 色差对照见 `tests/reference.py`，
两档色标的分段数/耗时/色差基准见 `bench/bench_ramp.py`。

