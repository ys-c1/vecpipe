# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`cli` 命令行。

描边端帽：`geom.stroke(points, width, cap=...)` 支持 `butt`（默认，与旧版逐字节一致）、
`round`、`square`，圆帽弦数由 `cap_segments` 控制；`geom.cap_area` 给手算端帽面积，
`geom.cap_area_error_bound` 给轮廓面积与手算面积之差的上界。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
make test
make bench   # 端帽像素与耗时基准，报告写入 artifacts/cap_bench.txt
```
