"""裁剪比例统计：按窗口与图形的交并关系算解析比例，逐像素统计对照并给误差上界。

解析比例：对每个窗口 W 与图形并集 S（假设各图形互不重叠），
    IoU = |W ∩ S| / |W ∪ S|，其中 |W ∩ S| 由 geom.clip_convex 精确裁出。
逐像素对照：在 W ∪ S 的包围盒上布网格，逐像素分类（交/并/外），
    边界穿过的像素记为歧义像素，误差上界 = 0.5 * 像素面积 * (歧义交 + 歧义并) / 并面积估计。
"""
import math
import time

from . import geom


def signed_area(poly):
    """鞋带公式，逆时针为正。"""
    total = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return 0.5 * total


def validate_window(window, index):
    """校验单个窗口，空窗口或面积非正时报错并指出窗口号；返回窗口面积。"""
    if len(window) < 3:
        raise ValueError("窗口 %d 为空：顶点数 %d，不足 3 个" % (index, len(window)))
    area = signed_area(window)
    if area <= 0.0:
        raise ValueError("窗口 %d 面积为负或为零（%.6g），顶点需逆时针" % (index, area))
    return area


def clip_ratio(shapes, window, index=0):
    """窗口与图形的交并比，返回 (交面积, 并面积, IoU)。"""
    w_area = validate_window(window, index)
    s_area = sum(abs(signed_area(poly)) for poly in shapes)
    inter = 0.0
    for poly in shapes:
        clipped = geom.clip_convex(poly, window)
        if clipped:
            inter += abs(signed_area(clipped))
    union = w_area + s_area - inter
    return inter, union, (inter / union if union > 0.0 else 0.0)


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _seg_cross(p1, p2, p3, p4):
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _seg_hits_box(p, q, x0, y0, x1, y1):
    """线段是否与闭合像素方块相交（含端点落入与穿边）。"""
    if (x0 <= p[0] <= x1 and y0 <= p[1] <= y1) or (x0 <= q[0] <= x1 and y0 <= q[1] <= y1):
        return True
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        if _seg_cross(p, q, corners[i], corners[(i + 1) % 4]):
            return True
    return False


def pixel_ratio(shapes, window, width, height, index=0):
    """逐像素对照统计，返回 (交面积估计, 并面积估计, 比例误差上界)。

    像素四角对窗口与图形逐一定点判定；若四角分类一致且无任何边穿过该像素，
    则分类确定，否则记为歧义像素。歧义像素按半格计入估计，误差上界由
    |r - r̂| <= (eI + eU) / Û 给出，eI/eU 为歧义像素各贡献的半格面积。
    """
    validate_window(window, index)
    polys = [window] + [p for p in shapes if len(p) >= 3]
    xs = [p[0] for poly in polys for p in poly]
    ys = [p[1] for poly in polys for p in poly]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    spanx, spany = maxx - minx, maxy - miny
    if spanx <= 0.0 or spany <= 0.0:
        raise ValueError("窗口 %d 与图形的并集包围盒退化" % index)
    cell = (spanx / width) * (spany / height)

    edges = []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            edges.append((poly[i], poly[(i + 1) % n]))

    inter_est = union_est = 0.0
    inter_amb = union_amb = 0
    for row in range(height):
        y0 = miny + spany * row / height
        y1 = miny + spany * (row + 1) / height
        for col in range(width):
            x0 = minx + spanx * col / width
            x1 = minx + spanx * (col + 1) / width
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            in_w = [geom.point_in_poly(window, cx, cy) for cx, cy in corners]
            in_s = [any(geom.point_in_poly(poly, cx, cy) for poly in shapes)
                    for cx, cy in corners]
            inter = [w and s for w, s in zip(in_w, in_s)]
            union = [w or s for w, s in zip(in_w, in_s)]
            cut = any(_seg_hits_box(p, q, x0, y0, x1, y1) for p, q in edges)
            if not cut and all(v == inter[0] for v in inter):
                inter_est += 1.0 if inter[0] else 0.0
            else:
                inter_est += sum(inter) / 4.0
                inter_amb += 1
            if not cut and all(v == union[0] for v in union):
                union_est += 1.0 if union[0] else 0.0
            else:
                union_est += sum(union) / 4.0
                union_amb += 1
    inter_area = inter_est * cell
    union_area = union_est * cell
    bound = 0.5 * cell * (inter_amb + union_amb) / union_area if union_area > 0.0 else 1.0
    return inter_area, union_area, bound


def grid_windows(count, bbox):
    """在包围盒上铺 count 个矩形窗口（近方形网格，逆时针）。"""
    if count < 1:
        raise ValueError("窗口数必须为正")
    minx, miny, maxx, maxy = bbox
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    windows = []
    for r in range(rows):
        for c in range(cols):
            if len(windows) >= count:
                break
            x0 = minx + (maxx - minx) * c / cols
            x1 = minx + (maxx - minx) * (c + 1) / cols
            y0 = miny + (maxy - miny) * r / rows
            y1 = miny + (maxy - miny) * (r + 1) / rows
            windows.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return windows


def measure(shapes, windows, pix_w=48, pix_h=48):
    """对一档窗口逐一统计，返回汇总：比例、逐像素对照、误差上界、耗时。"""
    t0 = time.perf_counter()
    inter = union = 0.0
    pix_inter = pix_union = 0.0
    pix_err_area = 0.0
    max_dev = 0.0
    max_bound = 0.0
    for i, window in enumerate(windows):
        ai, au, ri = clip_ratio(shapes, window, i)
        ei, eu, bi = pixel_ratio(shapes, window, pix_w, pix_h, i)
        inter += ai
        union += au
        pix_inter += ei
        pix_union += eu
        pix_err_area += bi * eu  # 逐窗口 (eI + eU) 累加，供汇总上界使用
        est = ei / eu if eu > 0.0 else 0.0
        max_dev = max(max_dev, abs(ri - est))
        max_bound = max(max_bound, bi)
    elapsed = time.perf_counter() - t0
    return {
        "windows": len(windows),
        "ratio": inter / union if union > 0.0 else 0.0,
        "pixel_ratio": pix_inter / pix_union if pix_union > 0.0 else 0.0,
        "err_bound": pix_err_area / pix_union if pix_union > 0.0 else 1.0,
        "max_window_bound": max_bound,
        "max_dev": max_dev,
        "elapsed": elapsed,
    }
