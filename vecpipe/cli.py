"""命令行入口。"""
import argparse
import json
import sys

from . import config, pipeline, raster, stats

SCENE = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]


def _parse_edges(text):
    edges = [float(x) for x in text.split(",") if x.strip()]
    stats.validate_edges(edges)
    return edges


def _print_stats(image, args):
    rows, cols = len(image), len(image[0])
    g = args.fine_grid
    if g > rows or g > cols:
        raise ValueError("细档网格 %d 密于图像 %dx%d" % (g, cols, rows))
    if args.coarse_grid > rows or args.coarse_grid > cols:
        raise ValueError("粗档网格 %d 密于图像 %dx%d" % (args.coarse_grid, cols, rows))
    if args.edges:
        edges = _parse_edges(args.edges)
    else:
        # 桶边要同时覆盖两档：粗网格的块最大，按粗档单块上界估算
        g = min(args.coarse_grid, args.fine_grid)
        cap = ((cols + g - 1) // g) * ((rows + g - 1) // g)
        edges = stats.default_edges(cap)
    grids = ((args.coarse_grid, args.coarse_grid),
             (args.fine_grid, args.fine_grid))
    report = stats.two_tier_report(image, edges, coarse=grids[0], fine=grids[1])
    for label in ("coarse", "fine"):
        print("== %s ==" % label)
        print(stats.format_report(report[label]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vecpipe")
    sub = ap.add_subparsers(dest="cmd")
    render = sub.add_parser("render")
    render.add_argument("--config", default="{}")
    render.add_argument("--out", default="out.pgm")
    render.add_argument("--stats", action="store_true",
                        help="输出图块面积分桶直方图与逐块手算复核（只读，不影响 PGM）")
    render.add_argument("--coarse-grid", type=int, default=4,
                        help="粗档网格边长（块数 = 边长平方）")
    render.add_argument("--fine-grid", type=int, default=16,
                        help="细档网格边长（块数 = 边长平方）")
    render.add_argument("--edges", default=None,
                        help="逗号分隔的桶边，如 0,1,4,16,64；默认按 2 的幂生成")
    sub.add_parser("info")
    args = ap.parse_args(argv)

    if args.cmd == "info":
        print(json.dumps(config.DEFAULTS, ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "render":
        raw = json.loads(args.config)
        raw.setdefault("output", args.out)
        image = pipeline.run(SCENE, raw)
        raster.save_pgm(raw["output"], image)
        print("on=%d" % raster.count_on(image))
        if args.stats:
            try:
                _print_stats(image, args)
            except ValueError as exc:
                print("统计参数错误: %s" % exc, file=sys.stderr)
                return 2
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
