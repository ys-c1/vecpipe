"""管线：配置 -> 场景变换 -> 光栅 -> 着色 -> 后处理 -> 导出。"""
import math

from . import config, geom, raster, shading, post


def transform(points, scale, rotate, dx=0.0, dy=0.0):
    c, s = math.cos(rotate), math.sin(rotate)
    out = []
    for x, y in points:
        out.append((scale * (x * c - y * s) + dx, scale * (x * s + y * c) + dy))
    return out


def run(scene, raw_cfg=None):
    cfg = config.parse(raw_cfg)
    image = raster.new_image(cfg["width"], cfg["height"])
    moved = [transform(poly, cfg["scale"], cfg["rotate"]) for poly in scene]
    raster.fill(image, moved, cfg["supersample"])
    shading.apply(image, cfg["shading"])
    image = post.gamma(image, cfg["gamma"])
    image = post.blur(image, cfg["blur"])
    return image
