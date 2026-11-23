"""图集装箱：按高度降序入箱，输出每块坐标与浪费率。

两种布局：

* ``hand_layout`` —— 手摆基线，按输入顺序做 next-fit 货架摆放；这就是现有
  的手摆布局，关闭装箱时原样输出，逐字节不变。
* ``pack_layout`` —— 装箱，先按高度降序（等高保持输入顺序）排序，再做
  first-fit 货架摆放，最后按原始输入顺序输出每块坐标。

浪费率统一定义为 ``1 - 图块总面积 / (箱宽 × 实际占用高度)``，两种布局用同一
口径，便于直接对照。非法输入（图块超出箱体、编号重复等）抛
:class:`AtlasError`，错误里带块号。
"""
import time
from collections import namedtuple

Tile = namedtuple("Tile", "id w h")
Placement = namedtuple("Placement", "id x y w h order")


class AtlasError(ValueError):
    """图集装箱的输入或摆放错误；``tile_id`` 指出出错的块号。"""

    def __init__(self, reason, tile_id=None, index=None):
        self.reason = reason
        self.tile_id = tile_id
        self.index = index
        msg = reason
        if tile_id is not None:
            msg += "：块号 %s" % (tile_id,)
        if index is not None:
            msg += "（第 %d 块）" % index
        super().__init__(msg)


def _positive_int(name, value, tile_id=None, index=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AtlasError("%s 必须是整数" % name, tile_id, index)
    if value <= 0:
        raise AtlasError("%s 必须为正" % name, tile_id, index)
    return value


def parse_tiles(raw):
    """把 ``{"id", "w", "h"}`` 字典或 ``Tile`` 列表规整成 ``Tile`` 列表。

    编号必须存在且唯一；宽高必须是正整数。任何问题都抛 ``AtlasError``，
    重复编号与非法尺寸会带上块号。
    """
    if not isinstance(raw, (list, tuple)):
        raise AtlasError("tiles 必须是列表")
    if not raw:
        raise AtlasError("图块列表为空")
    tiles = []
    seen = set()
    for i, item in enumerate(raw):
        pos = i + 1
        if isinstance(item, Tile):
            tid, w, h = item
        elif isinstance(item, dict):
            missing = [k for k in ("id", "w", "h") if k not in item]
            if missing:
                raise AtlasError("图块缺少字段 %s" % ",".join(missing),
                                 item.get("id"), pos)
            tid, w, h = item["id"], item["w"], item["h"]
        else:
            raise AtlasError("图块必须是对象或 Tile", index=pos)
        if tid is None:
            raise AtlasError("图块编号不能为空", index=pos)
        try:
            hash(tid)
        except TypeError:
            raise AtlasError("图块编号必须可哈希", tid, pos)
        _positive_int("宽度 w", w, tid, pos)
        _positive_int("高度 h", h, tid, pos)
        if tid in seen:
            raise AtlasError("重复编号", tid, pos)
        seen.add(tid)
        tiles.append(Tile(tid, w, h))
    return tiles


def _check_fits(tiles, width, height, check_height):
    for i, tile in enumerate(tiles):
        if tile.w > width:
            raise AtlasError("图块宽度超出箱体", tile.id, i + 1)
        if check_height and tile.h > height:
            raise AtlasError("图块高度超出箱体", tile.id, i + 1)


def hand_layout(tiles, width):
    """手摆基线：按输入顺序 next-fit 摆进宽 ``width`` 的货架。

    这是关闭装箱时的布局，保持逐字节不变，也是装箱方案的对照基准。
    返回 ``(placements, used_height)``，``placements`` 与输入顺序一致。
    """
    x = y = 0
    shelf_h = 0
    placements = []
    for i, tile in enumerate(tiles):
        if x + tile.w > width:
            y += shelf_h
            x = 0
            shelf_h = 0
        placements.append(Placement(tile.id, x, y, tile.w, tile.h, i))
        x += tile.w
        if tile.h > shelf_h:
            shelf_h = tile.h
    return placements, y + shelf_h


def pack_layout(tiles, width, height):
    """装箱：按高度降序（等高保持输入顺序）做 first-fit 货架摆放。

    返回 ``(placements, used_height)``，``placements`` 按原始输入顺序排列，
    ``order`` 字段记录入箱次序。放置时若累计高度超过箱体高度，抛
    ``AtlasError`` 并指出该块块号。
    """
    order = sorted(range(len(tiles)), key=lambda i: -tiles[i].h)
    shelves = []          # {"x", "y", "h", "rem"}
    placements = [None] * len(tiles)
    used_h = 0
    for seq, i in enumerate(order):
        tile = tiles[i]
        target = None
        for shelf in shelves:
            # 高度降序保证已有货架都装得下当前块，只需看剩余宽度。
            if shelf["rem"] >= tile.w:
                target = shelf
                break
        if target is None:
            if used_h + tile.h > height:
                raise AtlasError("装箱后超出箱体高度", tile.id, i + 1)
            target = {"x": 0, "y": used_h, "h": tile.h, "rem": width}
            shelves.append(target)
            used_h += tile.h
        placements[i] = Placement(tile.id, target["x"], target["y"],
                                  tile.w, tile.h, seq)
        target["x"] += tile.w
        target["rem"] -= tile.w
    return placements, used_h


def summarize(tiles, placements, width, used_height):
    """统计浪费：``area`` 取箱宽 × 实际占用高度。"""
    used_area = sum(t.w * t.h for t in tiles)
    area = width * used_height
    waste = area - used_area
    rate = waste / area if area else 0.0
    return {
        "count": len(tiles),
        "bin_width": width,
        "used_height": used_height,
        "used_area": used_area,
        "area": area,
        "waste": waste,
        "waste_rate": rate,
        "shelves": len({p.y for p in placements}),
    }


def _placement_dict(p):
    return {"id": p.id, "x": p.x, "y": p.y, "w": p.w, "h": p.h, "order": p.order}


def report(raw_tiles, width, height, pack=True):
    """生成一份布局报告：每块坐标、浪费率、手摆对照与降低幅度。

    ``pack=False`` 时输出手摆基线，``placements`` 与 ``hand_layout`` 完全一致。
    """
    tiles = parse_tiles(raw_tiles)
    width = _positive_int("箱体宽度 width", width)
    height = _positive_int("箱体高度 height", height)
    # 手摆基线只受箱宽约束；箱高只在装箱路径上约束。
    _check_fits(tiles, width, height, check_height=bool(pack))

    hand_pl, hand_h = hand_layout(tiles, width)
    hand_stats = summarize(tiles, hand_pl, width, hand_h)

    if pack:
        placements, used_h = pack_layout(tiles, width, height)
    else:
        placements, used_h = hand_pl, hand_h
    stats = summarize(tiles, placements, width, used_h)

    hand_rate = hand_stats["waste_rate"]
    chosen_rate = stats["waste_rate"]
    reduction = (hand_rate - chosen_rate) / hand_rate if hand_rate else 0.0
    return {
        "packed": bool(pack),
        "bin": {"width": width, "height": height},
        "placements": [_placement_dict(p) for p in placements],
        "stats": stats,
        "hand": {
            "placements": [_placement_dict(p) for p in hand_pl],
            "stats": hand_stats,
        },
        "comparison": {
            "hand_waste_rate": hand_rate,
            "pack_waste_rate": chosen_rate,
            "reduction": reduction,
            "target_reduction": 0.2,
            "meets_target": reduction >= 0.2,
        },
    }


def timed_report(raw_tiles, width, height, pack=True):
    """``report`` 加上装箱耗时（毫秒）。手摆基线耗时也一并给出。"""
    tiles = parse_tiles(raw_tiles)
    t0 = time.perf_counter()
    hand_layout(tiles, width)
    hand_ms = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    out = report(tiles, width, height, pack=pack)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    out["hand_ms"] = hand_ms
    out["pack_ms"] = elapsed_ms
    return out


def format_layout(placements):
    """把坐标按输入顺序序列化成稳定的文本行，用于逐字节对照。"""
    rows = []
    for p in placements:
        if isinstance(p, dict):
            rows.append("%s %d %d %d %d\n"
                        % (p["id"], p["x"], p["y"], p["w"], p["h"]))
        else:
            rows.append("%s %d %d %d %d\n" % (p.id, p.x, p.y, p.w, p.h))
    return "".join(rows)
