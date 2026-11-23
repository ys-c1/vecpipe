# vecpipe

纯 Python 的矢量渲染小引擎，无第三方依赖。

模块：`config` 配置校验、`geom` 几何（含鞋带公式 `polygon_area`）、`raster` 光栅化、`shading` 着色、`post` 后处理、`pipeline` 管线、`stats` 面积分桶统计、`cli` 命令行。

用法：

```
python3 -m vecpipe.cli info
python3 -m vecpipe.cli render --config '{"width":32,"height":32}' --out out.pgm
make test
```

## 图块面积分桶统计

把图像按网格切成图块（tile），逐块数点亮像素得到面积，再按桶边分桶出直方图，
并用一条完全独立的逐块手算路径复核落桶与桶计数、给出误差上界。统计只读取
图像，不触碰渲染管线与 PGM 输出：不加 `--stats` 时产物与以往逐字节相同。

```
python3 -m vecpipe.cli render --stats
python3 -m vecpipe.cli render --stats --coarse-grid 4 --fine-grid 16 \
    --edges 0,1,4,16,64,256
python3 tools/area_hist_demo.py
```

- 两档图块数各报：图块数、桶数、非空桶数、各桶块数、直方图/手算耗时、误差上界。
- 桶区间左闭右开（最后一桶右端封闭）。桶边为负或未严格递增（区间重叠/倒挂）
  一律报错，并指出桶号（如 `第 2 号桶边为负`、`第 1 号桶区间非法`）。
- 像素计数是整数且两条路径同输入同运算，实测最大绝对误差为 0；报告中的误差
  上界为 `max_abs_error + max_area·ε`，作为浮点口径的保守上界。

