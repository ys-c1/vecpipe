"""命令行入口。"""
import argparse
import json
import sys

from . import clipstat, config, pipeline, raster

SCENE = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vecpipe")
    sub = ap.add_subparsers(dest="cmd")
    render = sub.add_parser("render")
    render.add_argument("--config", default="{}")
    render.add_argument("--out", default="out.pgm")
    stat = sub.add_parser("clipstat")
    stat.add_argument("--config", default="{}")
    stat.add_argument("--tiers", default="4,64", help="两档窗口数，逗号分隔")
    stat.add_argument("--pixels", type=int, default=48, help="逐像素对照网格边长")
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
        return 0
    if args.cmd == "clipstat":
        cfg = config.parse(json.loads(args.config))
        scene = pipeline.transform(SCENE[0], cfg["scale"], cfg["rotate"])
        scene = [scene]
        xs = [p[0] for poly in scene for p in poly]
        ys = [p[1] for poly in scene for p in poly]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        for tier in [int(t) for t in args.tiers.split(",")]:
            windows = clipstat.grid_windows(tier, bbox)
            res = clipstat.measure(scene, windows, args.pixels, args.pixels)
            print("tier windows=%d ratio=%.6f pixel=%.6f err<=%.6f "
                  "max_dev=%.6f elapsed=%.3fs"
                  % (res["windows"], res["ratio"], res["pixel_ratio"],
                     res["err_bound"], res["max_dev"], res["elapsed"]))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
