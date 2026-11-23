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
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
