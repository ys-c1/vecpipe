# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
make test
```

## 容差去重

顶点预算按数量计算，近似重合的点会把它虚高。`dedup_tolerance`（或 CLI 的
`--dedup-tolerance`）给出正数容差后，管线会在变换前按欧氏距离合并顶点：

- 空间分桶找候选（网格边长 = 容差，查 3x3 邻域），再按距离连边取连通分量；
  每个分量保留原始下标最小的点，即“首次出现”的代表点。
- 结果与两两暴力配对 + 并查集完全一致（`geom.dedup_bruteforce` 对照），
  漏合并数为零由 `geom.count_missed_merges` 全点对核验。
- 代表点偏差上界：`容差 × (组内点数 − 1)`，由 `geom.dedup_stats` 报告实测值。
- 容差为 0 或负数直接报错（`ConfigError` / `ValueError`），关闭去重请省略该字段或传 `null`；
  关闭时顶点与管线输出逐字节不变。

基准：`python3 bench_dedup.py [n1 n2]`，默认 10k 与 200k 两档。
