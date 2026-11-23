"""管线：配置 -> 场景变换 -> 光栅 -> 着色 -> 后处理 -> 导出。"""
import math

from . import config, geom, raster, shading, post


def transform(points, scale, rotate, dx=0.0, dy=0.0):
    c, s = math.cos(rotate), math.sin(rotate)
    out = []
    for x, y in points:
        out.append((scale * (x * c - y * s) + dx, scale * (x * s + y * c) + dy))
    return out


def dedup_scene(scene, tolerance):
    """对每个多边形的顶点做容差去重，返回 (新场景, 统计)。

    统计里的 kept 就是后续预算应使用的顶点数；input 是去重前的虚高数量。
    tolerance 必须为正，0 或负数交给 geom.dedup 报错。
    """
    if tolerance is None:
        raise ValueError("tolerance 为 None 表示关闭去重，请勿调用 dedup_scene")
    out = []
    stats = {"input": 0, "kept": 0, "max_deviation": 0.0,
             "deviation_bound": 0.0, "polygons": len(scene)}
    for poly in scene:
        kept, groups = geom.dedup(poly, tolerance)
        if len(kept) < 3:
            raise ValueError("去重后多边形少于三个顶点（容差过大？）")
        piece = geom.dedup_stats(poly, tolerance, groups)
        stats["input"] += piece["input"]
        stats["kept"] += piece["kept"]
        stats["max_deviation"] = max(stats["max_deviation"],
                                     piece["max_deviation"])
        stats["deviation_bound"] = max(stats["deviation_bound"],
                                       piece["deviation_bound"])
        out.append(kept)
    stats["saved"] = stats["input"] - stats["kept"]
    return out, stats


def prepare_scene(scene, cfg):
    """按配置决定是否去重；关闭时原样返回场景对象，保证顶点逐字节不变。"""
    tolerance = cfg["dedup_tolerance"]
    if tolerance is None:
        return scene, None
    return dedup_scene(scene, tolerance)


def run(scene, raw_cfg=None, stats=None):
    cfg = config.parse(raw_cfg)
    scene, dedup_stats = prepare_scene(scene, cfg)
    if stats is not None:
        stats["dedup"] = dedup_stats
    image = raster.new_image(cfg["width"], cfg["height"])
    moved = [transform(poly, cfg["scale"], cfg["rotate"]) for poly in scene]
    raster.fill(image, moved, cfg["supersample"])
    shading.apply(image, cfg["shading"])
    image = post.gamma(image, cfg["gamma"])
    image = post.blur(image, cfg["blur"])
    return image
