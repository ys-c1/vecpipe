"""命令行入口。"""
import argparse
import json
import sys

from . import config, pipeline, raster

SCENE = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vecpipe")
    sub = ap.add_subparsers(dest="cmd")
    render = sub.add_parser("render")
    render.add_argument("--config", default="{}")
    render.add_argument("--out", default="out.pgm")
    render.add_argument("--dedup-tolerance", type=float, default=None,
                        help="顶点容差去重阈值（正数）；不传则关闭去重")
    sub.add_parser("info")
    args = ap.parse_args(argv)

    if args.cmd == "info":
        print(json.dumps(config.DEFAULTS, ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "render":
        raw = json.loads(args.config)
        raw.setdefault("output", args.out)
        if args.dedup_tolerance is not None:
            raw["dedup_tolerance"] = args.dedup_tolerance
        stats = {}
        try:
            image = pipeline.run(SCENE, raw, stats=stats)
        except config.ConfigError as exc:
            print("配置错误: %s" % exc, file=sys.stderr)
            return 2
        raster.save_pgm(raw["output"], image)
        dedup = stats.get("dedup")
        if dedup is not None:
            print("vertices=%d->%d saved=%d max_deviation=%.3e bound=%.3e"
                  % (dedup["input"], dedup["kept"], dedup["saved"],
                     dedup["max_deviation"], dedup["deviation_bound"]))
        print("on=%d" % raster.count_on(image))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
