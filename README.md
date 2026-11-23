# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
make test
```

## 覆盖率缓存

光栅化按三角形坐标缓存逐像素超采样覆盖率（`raster.CoverageCache`），同一三角形
重复绘制时直接复用，不再重算 `point_in_poly`。

- 键：三角形顶点坐标元组（浮点逐位相等才命中）；哈希为确定性 FNV-1a，不受
  `PYTHONHASHSEED` 影响。存储采用开放寻址（线性探测），值只保存三角形像素
  包围盒内的稀疏掩码（每像素一个采样点命中位掩码）。
- 配置：`cache_capacity`（条目上限，0 关闭，默认 0；范围 0–4096）、
  `cache_verify`（true 时每次命中都现算并与缓存逐像素对照，差异非零即抛
  `CacheVerifyError`）。
- 异常：探测链被其他条目占满抛 `CacheCollisionError`，容量耗尽抛
  `CacheFullError`，错误信息均指出槽位与冲突/写入条目。
- 缓存关闭时走原始逐像素路径，出图与启用前逐字节相同。
- 基准与命中率/耗时/缓存字节报告：`make bench`（结果写入
  `artifacts/coverage_cache_bench.json`）。
