# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`clipstat` 裁剪比例统计、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
python3 -m vecpipe.cli clipstat --tiers 4,64 --pixels 48
make test
```

`clipstat` 按窗口与图形的交并关系（IoU = |W∩S| / |W∪S|）算裁剪比例，
并用逐像素分类统计对照、给出比例误差上界；`--tiers` 给两档窗口数，各报比例与耗时。
窗口为空（顶点不足 3 个）或面积为负（顺时针）会报错并指出窗口号。
统计只在 `clipstat` 子命令内进行，`render` 出图不受影响。
