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


def stroke(points, width):
    if width <= 0:
        raise ValueError("width 必须为正")
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
            raise ValueError("折线出现重复点")
        nx, ny = -dy / norm * half, dx / norm * half
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    return left + right[::-1]
