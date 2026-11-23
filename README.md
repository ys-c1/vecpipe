# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`contour` 轮廓跟踪、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
python3 -m vecpipe.cli render --config '{"width":128,"height":96}' --trace
python3 -I bench/contour_bench.py      # 两档图幅（64/256）顶点数与耗时基准
make test
```

## 轮廓跟踪（`contour`）

逐像素法只能给出无序边界像素集合；`contour.trace_contours` 用方格跟踪
（Square Tracing，4 方位左拐/直行/右拐、状态去重闭合、光栅序重启）
输出**有序**轮廓点列。

- 前景 = 灰度 ≥ 128，图外按背景计；
- 逐像素两套静态集合：B4（4-邻域边界）、B8（8-邻域边界），B4 ⊆ B8；
- 跟踪访问集合 T 实测满足 B4 ⊆ T ⊆ B8（T ⊆ B8 由行走规则可证），
  仅对角接触背景的像素 B8 有而 4 方向行走不可达，差异逐点报告；
- 顶点差严格上界：K 条轮廓、每像素 4 个朝向状态，
  |V| ≤ 4·K·|B4|，即 |V|−|B4| ≤ (4K−1)·|B4|；
- 图为空（无前景）或全填满（无背景）抛 `ContourError` 并说明原因；
- `trace` 默认关闭，关闭时渲染与导出路径完全不变，出图逐字节一致。

