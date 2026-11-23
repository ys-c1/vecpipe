"""命令行入口。"""
import argparse
import json
import sys

from . import config, contour, pipeline, raster

SCENE = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vecpipe")
    sub = ap.add_subparsers(dest="cmd")
    render = sub.add_parser("render")
    render.add_argument("--config", default="{}")
    render.add_argument("--out", default="out.pgm")
    render.add_argument("--trace", action="store_true",
                        help="渲染后做 Moore 边界跟踪并与逐像素边界对照（不影响出图）")
    sub.add_parser("info")
    args = ap.parse_args(argv)

    if args.cmd == "info":
        print(json.dumps(config.DEFAULTS, ensure_ascii=False, sort_keys=True))
        return 0
    if args.cmd == "render":
        raw = json.loads(args.config)
        raw.setdefault("output", args.out)
        if args.trace:
            raw["trace"] = True
        image = pipeline.run(SCENE, raw)
        raster.save_pgm(raw["output"], image)
        print("on=%d" % raster.count_on(image))
        if raw.get("trace", False):
            try:
                report = contour.analyze(image)
            except contour.ContourError as exc:
                # 出图已逐字节写出；仅跟踪分析无法进行
                print("轮廓跟踪失败: %s" % exc, file=sys.stderr)
                return 2
            print(contour.format_report(report))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
