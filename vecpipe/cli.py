"""命令行入口。"""
import argparse
import json
import sys

from . import atlas, config, pipeline, raster

SCENE = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]


def _atlas(raw_tiles, width, height, pack):
    """图集装箱：打印每块坐标，再输出统计（浪费率、手摆对照、耗时）。"""
    try:
        report = atlas.timed_report(raw_tiles, width, height, pack=pack)
    except atlas.AtlasError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
    print(atlas.format_layout(report["placements"]), end="")
    print(json.dumps({"stats": report["stats"],
                      "hand": report["hand"]["stats"],
                      "comparison": report["comparison"],
                      "pack_ms": report["pack_ms"]},
                     ensure_ascii=False, sort_keys=True))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vecpipe")
    sub = ap.add_subparsers(dest="cmd")
    render = sub.add_parser("render")
    render.add_argument("--config", default="{}")
    render.add_argument("--out", default="out.pgm")
    sub.add_parser("info")
    packer = sub.add_parser("atlas")
    packer.add_argument("--tiles", required=True, help="图块 JSON 列表")
    packer.add_argument("--width", type=int, default=128)
    packer.add_argument("--height", type=int, default=4096)
    packer.add_argument("--no-pack", action="store_true", help="关闭装箱，输出手摆基线")
    args = ap.parse_args(argv)

    if args.cmd == "info":
        print(json.dumps(config.DEFAULTS, ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "atlas":
        return _atlas(json.loads(args.tiles), args.width, args.height,
                      not args.no_pack)
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
