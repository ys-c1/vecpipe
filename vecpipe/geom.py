"""几何：贝塞尔、折线、点在多边形内、凸窗裁剪、描边轮廓、容差去重。"""
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


def dedup(points, tolerance):
    """按容差合并顶点，保留每个合并组里首次出现的点。

    合并规则：两点欧氏距离 <= tolerance 即连边，再取连通分量；每个分量
    的代表点是其中原始下标最小的点。因此结果与“两两暴力配对 + 并查集”
    完全一致，不会漏合并。返回 (kept, groups)：
      kept   —— 代表点，按原始顺序排列，坐标原样保留首次出现的对象；
      groups —— 每个分量的原始下标列表，按代表点出现顺序排列。
    容差必须为正；0 或负数直接报错（关闭去重是调用方的事，不是传 0）。
    """
    tol = _check_tolerance(tolerance)
    if not points:
        return [], []
    n = len(points)
    parent = list(range(n))

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            # 小下标为根，代表点天然是首次出现的那个。
            if ri < rj:
                parent[rj] = ri
            else:
                parent[ri] = rj

    # 完全相同坐标先精确折叠：只给唯一坐标建桶，精确重复不会撑大邻域搜索。
    unique = []
    first_of = {}
    for i, p in enumerate(points):
        x, y = _finite_xy(p, i)
        j = first_of.get((x, y))
        if j is None:
            first_of[(x, y)] = i
            unique.append(i)
        else:
            union(i, j)

    # 桶边长取 tol，距离 <= tol 的唯一点必定落在 3x3 邻域内。
    buckets = {}
    for i in unique:
        x, y = points[i][0], points[i][1]
        cx, cy = _cell(x, y, tol)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for j in buckets.get((cx + dx, cy + dy), ()):
                    qx, qy = points[j][0], points[j][1]
                    if (x - qx) * (x - qx) + (y - qy) * (y - qy) <= tol * tol:
                        union(i, j)
        buckets.setdefault((cx, cy), []).append(i)

    kept, groups = [], []
    slot = {}
    for i in range(n):
        root = find(i)
        if root not in slot:
            slot[root] = len(kept)
            kept.append(points[root])
            groups.append([])
        groups[slot[root]].append(i)
    return kept, groups


def dedup_bruteforce(points, tolerance):
    """去重的暴力对照实现：所有点对逐一比较，距离 <= 容差则合并。

    返回格式与 dedup 相同，仅用于验证，不用于生产路径。
    """
    tol = _check_tolerance(tolerance)
    n = len(points)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, p in enumerate(points):
        xi, yi = _finite_xy(p, i)
        for j in range(i):
            xj, yj = _finite_xy(points[j], j)
            if (xi - xj) * (xi - xj) + (yi - yj) * (yi - yj) <= tol * tol:
                ri, rj = find(i), find(j)
                if ri != rj:
                    if ri < rj:
                        parent[rj] = ri
                    else:
                        parent[ri] = rj
    kept, groups = [], []
    slot = {}
    for i in range(n):
        root = find(i)
        if root not in slot:
            slot[root] = len(kept)
            kept.append(points[root])
            groups.append([])
        groups[slot[root]].append(i)
    return kept, groups


def dedup_stats(points, tolerance, groups=None):
    """返回去重统计：输入点数、保留点数、代表点最大偏差与上界。

    代表点偏差 = 组内点到该组代表点的欧氏距离；上界用三角不等式
    `容差 * (组大小 - 1)` 给出（合并链最长不超过组大小 - 1 条边）。
    需要用全点对确认“漏合并为零”时另见 count_missed_merges。
    """
    tol = _check_tolerance(tolerance)
    if groups is None:
        _, groups = dedup(points, tolerance)
    reps = [points[g[0]] for g in groups]
    max_dev = 0.0
    bound = 0.0
    for gi, g in enumerate(groups):
        rx, ry = _finite_xy(reps[gi], g[0])
        for i in g:
            x, y = _finite_xy(points[i], i)
            d = math.hypot(x - rx, y - ry)
            if d > max_dev:
                max_dev = d
        bound = max(bound, tol * max(0, len(g) - 1))
    return {
        "input": len(points),
        "kept": len(groups),
        "max_deviation": max_dev,
        "deviation_bound": bound,
    }


def count_missed_merges(points, tolerance, groups):
    """全点对检查：距离 <= 容差但分属不同组的点对数量。"""
    tol = _check_tolerance(tolerance)
    group_of = [0] * len(points)
    for gi, g in enumerate(groups):
        for i in g:
            group_of[i] = gi
    missed = 0
    for i in range(len(points)):
        xi, yi = _finite_xy(points[i], i)
        for j in range(i):
            xj, yj = _finite_xy(points[j], j)
            if (xi - xj) * (xi - xj) + (yi - yj) * (yi - yj) <= tol * tol:
                if group_of[i] != group_of[j]:
                    missed += 1
    return missed


def _check_tolerance(tolerance):
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("tolerance 必须是数字")
    tol = float(tolerance)
    if not math.isfinite(tol):
        raise ValueError("tolerance 必须是有限数")
    if tol <= 0.0:
        raise ValueError("tolerance 必须为正；0 或负数不能表示去重，"
                         "要关闭去重请使用 dedup=False")
    return tol


def _finite_xy(p, idx):
    x, y = p[0], p[1]
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("第 %d 个顶点坐标不是有限数" % idx)
    return x, y


def _cell(x, y, tol):
    return (math.floor(x / tol), math.floor(y / tol))
