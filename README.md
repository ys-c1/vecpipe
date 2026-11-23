# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
make test
make bench
```

## 贝塞尔细分

`geom.flatten` 保留固定段数细分（默认 `segments=16`）。另有按弦高误差
自适应细分的 `geom.adaptive_flatten` / `geom.adaptive_leaves`，统一入口
为 `geom.flatten_curve` 与 `geom.flatten_path`：

- 判据：de Casteljau 在 t=0.5 递归二分，直到 `0.75·max(h1,h2) <= flatness`。
  该值是三次贝塞尔相对端点弦真实最大偏离的**严格解析上界**。
- 验证：`geom.max_chord_error` 与 4096 段细密参考折线对照，给出实测最大
  弦高误差（真实误差的紧下界），与解析上界一并报告，满足
  `实测 <= 上界 <= 容差`。
- 段号按递归前序（深度优先）编号，根段为第 0 段；`flatten_path` 跨曲线
  连续编号。容差为零、控制点完全重合（退化为点）、端点重合（弦长为零）
  均抛 `geom.FlattenError` 并在消息中指出段号。
- 配置项 `adaptive`（默认 `false`）、`flatness`（默认 `0.25`，严格为正）、
  `segments`（默认 `16`）。`adaptive=false` 时输出与固定段数路径逐字节相同。

`make bench` 输出两档曲率（缓弯/急弯）在两档容差下的段数、耗时与误差对照。
