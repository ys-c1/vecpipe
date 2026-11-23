"""图集装箱基准：两档图块数各报浪费率与耗时，并与手摆方案逐块对照。

运行：``python3 -I bench/bench_atlas.py``
输出：终端表格 + ``artifacts/atlas_bench.json``

检查项：
* 每块坐标合法：不越界、两两不重叠、编号齐全且各出现一次；
* 关闭装箱（``pack=False``）的输出与手摆基线逐字节相同；
* 装箱相对手摆的浪费率降幅不少于两成。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from vecpipe import atlas

BIN_WIDTH = 128
BIN_HEIGHT = 4096
REPS = 200

# 两档图块数。尺寸取常见的精灵/图标混合量级，含少量通栏长条。
TIERS = [
    {"name": "small", "count": 24, "seed": 2024},
    {"name": "large", "count": 120, "seed": 2024},
]
_WIDTHS = (8, 12, 16, 20, 24, 32, 40, 48, 64, 96)
_HEIGHTS = (8, 12, 16, 20, 24, 32, 40, 48, 64, 80)


def make_tiles(count, seed):
    """确定性 LCG 生成图块，避免依赖 ``random`` 的实现细节。"""
    state = seed

    def rnd(n):
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state % n

    return [{"id": "t%03d" % i,
             "w": _WIDTHS[rnd(len(_WIDTHS))],
             "h": _HEIGHTS[rnd(len(_HEIGHTS))]}
            for i in range(count)]


def validate(placements, tiles, width, height):
    """逐块校验：越界、重叠、编号唯一且齐全。返回校验结论。"""
    by_id = {t["id"]: t for t in tiles}
    seen = set()
    rects = []
    for p in placements:
        if p["id"] not in by_id:
            raise AssertionError("未知块号 %s" % p["id"])
        if p["id"] in seen:
            raise AssertionError("重复输出块号 %s" % p["id"])
        seen.add(p["id"])
        if p["w"] != by_id[p["id"]]["w"] or p["h"] != by_id[p["id"]]["h"]:
            raise AssertionError("块 %s 尺寸被改动" % p["id"])
        if p["x"] < 0 or p["y"] < 0 or p["x"] + p["w"] > width \
                or p["y"] + p["h"] > height:
            raise AssertionError("块 %s 越界" % p["id"])
        rects.append((p["x"], p["y"], p["w"], p["h"], p["id"]))
    if seen != set(by_id):
        raise AssertionError("输出缺块 %s" % (set(by_id) - seen))
    for i in range(len(rects)):
        x1, y1, w1, h1, id1 = rects[i]
        for j in range(i + 1, len(rects)):
            x2, y2, w2, h2, id2 = rects[j]
            if x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1:
                raise AssertionError("块 %s 与 %s 重叠" % (id1, id2))
    return True


def best_ms(tiles, width, height, pack):
    best = None
    last = None
    for _ in range(REPS):
        t0 = time.perf_counter()
        last = atlas.report(tiles, width, height, pack=pack)
        dt = (time.perf_counter() - t0) * 1000.0
        best = dt if best is None else min(best, dt)
    return last, best


def run_tier(tier):
    tiles = make_tiles(tier["count"], tier["seed"])
    packed, pack_ms = best_ms(tiles, BIN_WIDTH, BIN_HEIGHT, True)
    hand, hand_ms = best_ms(tiles, BIN_WIDTH, BIN_HEIGHT, False)

    # 关闭装箱：输出必须与手摆基线逐字节相同。
    off = atlas.report(tiles, BIN_WIDTH, BIN_HEIGHT, pack=False)
    off_bytes = atlas.format_layout(off["placements"])
    hand_bytes = atlas.format_layout(hand["placements"])
    assert off_bytes == hand_bytes, "关闭装箱时布局与手摆不一致"
    assert off["placements"] == hand["placements"]

    validate(packed["placements"], tiles, BIN_WIDTH, BIN_HEIGHT)
    validate(hand["placements"], tiles, BIN_WIDTH, BIN_HEIGHT)

    hand_rate = hand["stats"]["waste_rate"]
    pack_rate = packed["stats"]["waste_rate"]
    reduction = (hand_rate - pack_rate) / hand_rate if hand_rate else 0.0
    assert reduction >= 0.2, "降幅不足两成：%.2f%%" % (reduction * 100)

    return {
        "tier": tier["name"],
        "tiles": len(tiles),
        "bin_width": BIN_WIDTH,
        "hand_waste_rate": round(hand_rate, 4),
        "pack_waste_rate": round(pack_rate, 4),
        "reduction": round(reduction, 4),
        "hand_used_height": hand["stats"]["used_height"],
        "pack_used_height": packed["stats"]["used_height"],
        "hand_shelves": hand["stats"]["shelves"],
        "pack_shelves": packed["stats"]["shelves"],
        "hand_ms": round(hand_ms, 4),
        "pack_ms": round(pack_ms, 4),
        "meets_target": reduction >= 0.2,
        "offscreen_bytes_identical": off_bytes == hand_bytes,
        "validated": True,
        "placements": packed["placements"],
    }


def demo_errors():
    """演示两类必须报错并指出块号的情形。"""
    cases = [
        ("超出箱体宽度",
         [{"id": "a", "w": 8, "h": 8}, {"id": "big", "w": 256, "h": 8}],
         128, 4096),
        ("超出箱体高度",
         [{"id": "a", "w": 8, "h": 8}, {"id": "tall", "w": 8, "h": 9999}],
         128, 4096),
        ("重复编号",
         [{"id": "a", "w": 8, "h": 8}, {"id": "a", "w": 16, "h": 16}],
         128, 4096),
    ]
    out = []
    for label, tiles, width, height in cases:
        try:
            atlas.report(tiles, width, height, pack=True)
        except atlas.AtlasError as exc:
            out.append({"case": label, "tile_id": exc.tile_id,
                        "index": exc.index, "message": str(exc)})
        else:
            raise AssertionError("%s 未报错" % label)
    return out


def main():
    results = []
    for tier in TIERS:
        results.append(run_tier(tier))

    print("图集装箱基准（箱宽 %d，箱高 %d）" % (BIN_WIDTH, BIN_HEIGHT))
    print("%-6s %5s %10s %10s %8s %8s %8s %10s"
          % ("档位", "块数", "手摆浪费率", "装箱浪费率", "降幅",
             "手摆ms", "装箱ms", "关箱字节一致"))
    for r in results:
        print("%-6s %5d %9.2f%% %9.2f%% %7.1f%% %8.3f %8.3f %10s"
              % (r["tier"], r["tiles"], r["hand_waste_rate"] * 100,
                 r["pack_waste_rate"] * 100, r["reduction"] * 100,
                 r["hand_ms"], r["pack_ms"],
                 "是" if r["offscreen_bytes_identical"] else "否"))
    print()
    for r in results:
        print("档位 %s 每块坐标（按输入顺序）：" % r["tier"])
        for p in r["placements"]:
            print("  %s x=%d y=%d w=%d h=%d" %
                  (p["id"], p["x"], p["y"], p["w"], p["h"]))

    errors = demo_errors()
    print()
    print("错误路径：")
    for e in errors:
        print("  %s -> %s" % (e["case"], e["message"]))

    payload = {"bin": {"width": BIN_WIDTH, "height": BIN_HEIGHT},
               "tiers": results, "errors": errors}
    os.makedirs(os.path.join(ROOT, "artifacts"), exist_ok=True)
    with open(os.path.join(ROOT, "artifacts", "atlas_bench.json"), "w",
              encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
