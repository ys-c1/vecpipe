"""几何：贝塞尔、折线、点在多边形内、凸窗裁剪、描边轮廓。"""
import math


class FlattenError(ValueError):
    """自适应细分失败：零容差、控制点重合退化或超过最大深度。消息中带段号。"""


_MAX_DEPTH = 64


def bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def flatten(p0, p1, p2, p3, segments=16):
    if segments < 1:
        raise ValueError("segments 必须为正")
    return [bezier(p0, p1, p2, p3, i / segments) for i in range(segments + 1)]


def _split_decasteljau(p0, p1, p2, p3):
    """t=0.5 处把三次贝塞尔切成两半，返回左、右两组控制点。"""
    q0 = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
    q1 = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
    q2 = ((p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5)
    r0 = ((q0[0] + q1[0]) * 0.5, (q0[1] + q1[1]) * 0.5)
    r1 = ((q1[0] + q2[0]) * 0.5, (q1[1] + q2[1]) * 0.5)
    m = ((r0[0] + r1[0]) * 0.5, (r0[1] + r1[1]) * 0.5)
    return (p0, q0, r0, m), (m, r1, q2, p3)


def _point_line_distance(p, a, b):
    """点 p 到过 a、b 的无穷直线的垂直距离（弦高判据用的就是它）。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy)
    if norm == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(dx * (a[1] - p[1]) - dy * (a[0] - p[0])) / norm


def _check_flat(curve, seg_id, tol):
    """判一段是否够平。返回 (accepted, bound)，退化时抛带段号的错误。

    bound = 0.75*max(h1,h2) 是三次贝塞尔相对端点弦的真实最大偏离的严格
    上界：曲线点到弦的距离是凸组合 0.75*(1-t)t 上的一条贝塞尔，其控制
    多边形高为 h1、h2，凸包性质保证曲线不超出控制多边形。
    """
    p0, p1, p2, p3 = curve
    chord = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
    if chord == 0.0:
        # 弦退化为点，弦高判据无定义。
        if p0 == p1 == p2 == p3:
            raise FlattenError(
                "第 %d 段控制点完全重合，曲线退化为点，无法细分" % seg_id)
        raise FlattenError(
            "第 %d 段端点重合（弦长为零），弦高判据无定义，无法细分"
            % seg_id)
    h1 = _point_line_distance(p1, p0, p3)
    h2 = _point_line_distance(p2, p0, p3)
    bound = 0.75 * max(h1, h2)
    return bound <= tol, bound


def _validate_tol(tol, root_seg_id):
    if isinstance(tol, bool) or not isinstance(tol, (int, float)) \
            or not math.isfinite(tol):
        raise FlattenError("flatness 必须是有限正数")
    if tol <= 0.0:
        raise FlattenError(
            "第 %d 段 flatness 容差为零，细分永远无法收敛" % root_seg_id)


def _adaptive_recurse(curve, tol, seg_offset):
    """递归核心。返回 (leaves, node_count)。

    leaves: [(全局段号, (根参数域 t_lo, t_hi), 解析误差上界), ...]
    段号按递归前序（深度优先）编号，根段编号为 seg_offset。
    """
    _validate_tol(tol, seg_offset)
    counter = [0]
    leaves = []

    def recurse(sub, depth, t_lo, t_hi):
        seg_id = seg_offset + counter[0]
        counter[0] += 1
        accepted, bound = _check_flat(sub, seg_id, tol)
        if accepted:
            leaves.append((seg_id, (t_lo, t_hi), bound))
            return
        if depth >= _MAX_DEPTH:
            raise FlattenError(
                "第 %d 段细分深度超过上限 %d 仍未达到容差 %g"
                % (seg_id, _MAX_DEPTH, tol))
        left, right = _split_decasteljau(*sub)
        t_mid = (t_lo + t_hi) * 0.5
        recurse(left, depth + 1, t_lo, t_mid)
        recurse(right, depth + 1, t_mid, t_hi)

    recurse(tuple(curve), 0, 0.0, 1.0)
    leaves.sort(key=lambda item: item[1][0])
    return leaves, counter[0]


def adaptive_leaves(p0, p1, p2, p3, tol, seg_offset=0):
    """按弦高误差递归细分，返回 [(seg_id, (t_lo, t_hi), bound), ...]。

    每个叶子的 bound 是该段真实最大弦高误差的解析上界，必不超过 tol。
    """
    leaves, _node_count = _adaptive_recurse(
        (p0, p1, p2, p3), tol, seg_offset)
    return leaves


def adaptive_flatten(p0, p1, p2, p3, tol=0.25):
    """自适应弦高细分，返回与 flatten 同构的折线点列（含两端点）。"""
    leaves = adaptive_leaves(p0, p1, p2, p3, tol)
    points = [bezier(p0, p1, p2, p3, t_lo)
              for _seg_id, (t_lo, _t_hi), _bound in leaves]
    points.append((p3[0], p3[1]))
    return points


def flatten_curve(p0, p1, p2, p3, adaptive=False, segments=16, tol=0.25):
    """统一入口：adaptive=False 时逐字节走旧的固定段数路径。"""
    if adaptive:
        return adaptive_flatten(p0, p1, p2, p3, tol)
    return flatten(p0, p1, p2, p3, segments)


def flatten_path(curves, adaptive=False, segments=16, tol=0.25):
    """展平由多段三次贝塞尔首尾相接组成的路径，连接处不重复加点。

    段号跨曲线连续：第 k 条曲线的根段编号接续前面曲线的节点总数，
    退化报错因此能定位到整条路径上的全局段号。
    """
    if not curves:
        return []
    points = []
    seg_offset = 0
    for index, curve in enumerate(curves):
        if adaptive:
            leaves, node_count = _adaptive_recurse(curve, tol, seg_offset)
            seg_offset += node_count
            pts = [bezier(*curve, t_lo)
                   for _seg_id, (t_lo, _t_hi), _bound in leaves]
            pts.append(curve[3])
        else:
            pts = flatten(*curve, segments)
        points.extend(pts if index == 0 else pts[1:])
    return points


def _point_segment_distance(px, py, a, b):
    """点到有限线段的最短距离。"""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(px - ax, py - ay)
    u = ((px - ax) * dx + (py - ay) * dy) / length_sq
    u = min(1.0, max(0.0, u))
    qx, qy = ax + u * dx, ay + u * dy
    return math.hypot(px - qx, py - qy)


def max_chord_error(p0, p1, p2, p3, polyline, ref_segments=4096):
    """用细密均匀采样的参考折线对照，返回实测最大弦高误差。

    参考折线本身有 O(ref_segments^-4) 的残余误差，故实测值是真实误差的
    紧下界估计；严格上界用 adaptive_leaves 返回的解析 bound。
    """
    ref = flatten(p0, p1, p2, p3, ref_segments)
    worst = 0.0
    j = 0
    for x, y in ref:
        while j + 2 < len(polyline):
            d_cur = _point_segment_distance(
                x, y, polyline[j], polyline[j + 1])
            d_nxt = _point_segment_distance(
                x, y, polyline[j + 1], polyline[j + 2])
            if d_nxt <= d_cur:
                j += 1
            else:
                break
        d = _point_segment_distance(x, y, polyline[j], polyline[j + 1])
        if d > worst:
            worst = d
    return worst


def adaptive_error_bound(p0, p1, p2, p3, tol):
    """自适应细分后各叶子解析上界中的最大值（必然 <= tol）。"""
    leaves = adaptive_leaves(p0, p1, p2, p3, tol)
    return max(bound for _seg_id, _span, bound in leaves)


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
