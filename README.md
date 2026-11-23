# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`atlas` 图集装箱、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
python3 -m vecpipe.cli atlas --tiles '[{"id":"a","w":32,"h":64},{"id":"b","w":96,"h":64}]'
python3 -m vecpipe.cli atlas --tiles '[...]' --no-pack   # 关闭装箱，输出手摆基线
python3 -I bench/bench_atlas.py                          # 两档图块数：浪费率、耗时
make test
```

## 图集装箱（`atlas`）

* `hand_layout`：手摆基线，按输入顺序 next-fit 货架摆放；`--no-pack` 时原样输出。
* `pack_layout`：装箱，按高度降序（等高保持输入顺序）first-fit 入箱，再按原输入
  顺序回填每块坐标。
* 浪费率统一为 `1 - 图块总面积 / (箱宽 × 实际占用高度)`，两种布局同口径对照。
* 图块超出箱体、编号重复、宽高非正、字段缺失都会抛 `AtlasError` 并指出块号。
