"""几何：贝塞尔、折线、点在多边形内、凸窗裁剪、描边轮廓。"""
import math


def bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def flatten(p0, p1, p2, p3, segments=16):
    if segments < 1:
        raise ValueError("segments 必须为正")
    return [bezier(p0, p1, p2, p3, i / segments) for i in range(segments + 1)]


def polyline_length(points):
    total = 0.0
    for i in range(len(points) - 1):
        dx = points[i + 1][0] - points[i][0]
        dy = points[i + 1][1] - points[i][1]
        total += math.hypot(dx, dy)
    return total


def point_in_poly(points, px, py):
    inside = False
    n = len(points)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        if (ay > py) == (by > py):
            continue
        t = (py - ay) / (by - ay)
        if ax + (bx - ax) * t > px:
            inside = not inside
    return inside


def clip_convex(poly, window):
    if len(poly) < 3 or len(window) < 3:
        raise ValueError("裁剪需要至少三个顶点")
    out = list(poly)
    for i in range(len(window)):
        ax, ay = window[i]
        bx, by = window[(i + 1) % len(window)]
        edge = (bx - ax, by - ay)

        def inside(p):
            return edge[0] * (p[1] - ay) - edge[1] * (p[0] - ax) >= 0

        nxt = []
        for j in range(len(out)):
            cur = out[j]
            prv = out[j - 1]
            if inside(cur):
                if not inside(prv):
                    nxt.append(_intersect(prv, cur, (ax, ay), (bx, by)))
                nxt.append(cur)
            elif inside(prv):
                nxt.append(_intersect(prv, cur, (ax, ay), (bx, by)))
        out = nxt
        if not out:
            break
    return out


def _intersect(p, q, a, b):
    x1, y1 = p
    x2, y2 = q
    x3, y3 = a
    x4, y4 = b
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return q
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)


CAPS = ("butt", "round", "square")


def stroke(points, width, cap="butt", cap_segments=16):
    if width <= 0:
        raise ValueError("width 必须为正，当前为 %r" % (width,))
    if cap not in CAPS:
        raise ValueError("cap 只能是 %s，当前为 %r" % ("/".join(CAPS), cap))
    if cap_segments < 2:
        raise ValueError("cap_segments 必须 >= 2")
    if len(points) < 2:
        raise ValueError("描边至少需要两个端点，当前 %d 个" % len(points))
    half = width * 0.5
    left, right = [], []
    for i, (x, y) in enumerate(points):
        if i + 1 < len(points):
            dx = points[i + 1][0] - x
            dy = points[i + 1][1] - y
        else:
            dx = x - points[i - 1][0]
            dy = y - points[i - 1][1]
        norm = math.hypot(dx, dy)
        if norm < 1e-12:
            j = i + 1 if i + 1 < len(points) else i - 1
            raise ValueError("折线端点 %d 与 %d 重复（间距小于 1e-12）" % (min(i, j), max(i, j)))
        nx, ny = -dy / norm * half, dx / norm * half
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    if cap == "butt":
        return left + right[::-1]
    return left + _cap(points[-1], points[-2], half, cap, cap_segments) \
        + right[::-1] + _cap(points[0], points[1], half, cap, cap_segments)


def _cap(tip, anchor, half, cap, cap_segments):
    """端帽顶点：从一侧轮廓绕端点法向-切向扇面到另一侧。

    外向切向 t = (tip - anchor) / |tip - anchor|，法向 n 为 t 左转 90 度。
    返回的顶点按轮廓绕行方向排列（+n 一侧到 -n 一侧），可直接插入
    left 末尾与 right 末尾之间，或 right 开头与 left 开头之间。
    """
    dx, dy = tip[0] - anchor[0], tip[1] - anchor[1]
    norm = math.hypot(dx, dy)
    if norm < 1e-12:
        raise ValueError("端点 %r 与相邻端点重复，无法确定端帽方向" % (tip,))
    tx, ty = dx / norm, dy / norm
    nx, ny = -ty, tx
    if cap == "square":
        return [
            (tip[0] + (nx + tx) * half, tip[1] + (ny + ty) * half),
            (tip[0] + (-nx + tx) * half, tip[1] + (-ny + ty) * half),
        ]
    # round：从 +n 经 +t 到 -n 的半圆扇面，cap_segments 段弦
    pts = []
    for j in range(1, cap_segments):
        a = math.pi * j / cap_segments
        ca, sa = math.cos(a), math.sin(a)
        pts.append((tip[0] + half * (ca * nx + sa * tx),
                    tip[1] + half * (ca * ny + sa * ty)))
    return pts


def polygon_area(points):
    s = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def cap_area(width, cap="butt"):
    """两个端帽的解析（手算）面积。"""
    if cap == "butt":
        return 0.0
    if cap == "square":
        return width * width
    if cap == "round":
        return math.pi * width * width / 4.0
    raise ValueError("cap 只能是 %s，当前为 %r" % ("/".join(CAPS), cap))


def cap_area_error_bound(width, cap="butt", cap_segments=16):
    """端帽轮廓面积与解析面积之差的上界。

    round 端帽用 cap_segments 段弦逼近半圆：由 sin x >= x - x^3/6，
    每个半圆面积亏 <= r^2 * pi^3 / (12 k^2)，两个端帽合计 <= r^2 * pi^3 / (6 k^2)。
    butt / square 无逼近误差，上界为 0（只剩浮点舍入）。
    """
    if cap == "round":
        r = width * 0.5
        return r * r * math.pi ** 3 / (6.0 * cap_segments * cap_segments)
    if cap in ("butt", "square"):
        return 0.0
    raise ValueError("cap 只能是 %s，当前为 %r" % ("/".join(CAPS), cap))
