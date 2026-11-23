"""面积统计：图块分桶直方图、逐块手算复核与误差上界。

图块（tile）把整幅图像按 nx*ny 的网格切开，每块的“面积”取块内点亮
（灰度 >= threshold）的像素数。统计只读取图像，绝不修改图像，因此关闭
统计时渲染产物与不启用统计逐字节相同。

桶区间采用左闭右开：[e0,e1), [e1,e2), ..., [e{k-2},e{k-1}]（最后一个桶
右端封闭）。桶边必须非负且严格递增，否则报错并指出桶号。
"""
import sys
import time


def _as_pos_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("%s 必须是正整数" % name)
    return value


def validate_edges(edges):
    """校验桶边：非负、至少两条、严格递增（重叠/倒挂即非法），返回桶数。"""
    if not isinstance(edges, (list, tuple)) or len(edges) < 2:
        raise ValueError("桶边至少需要两个数值")
    for i, e in enumerate(edges):
        if isinstance(e, bool) or not isinstance(e, (int, float)):
            raise ValueError("第 %d 号桶边不是数值" % i)
        if e < 0:
            raise ValueError("第 %d 号桶边为负: %r" % (i, e))
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            raise ValueError(
                "第 %d 号桶区间非法: 边界 %r 未严格大于 %r（区间重叠或倒挂）"
                % (i - 1, edges[i], edges[i - 1]))
    return len(edges) - 1


def _bucket_index(area, edges):
    """与手算路径同构的落桶：线性扫描，最后一个桶右端封闭。"""
    if area < edges[0]:
        return -1
    last = len(edges) - 2
    for i in range(last):
        if area < edges[i + 1]:
            return i
    if area <= edges[-1]:
        return last
    return -1  # 溢出，无桶可落


def tile_areas(image, nx, ny, threshold=128):
    """按 nx*ny 网格切块，逐块统计点亮像素数，返回 (areas, rows, cols)。

    图像边长不能整除网格时，余数并入最后一行/列的块。
    """
    nx = _as_pos_int("nx", nx)
    ny = _as_pos_int("ny", ny)
    rows = len(image)
    cols = len(image[0]) if rows else 0
    if rows == 0 or cols == 0:
        raise ValueError("空图像无法分块")
    if nx > cols or ny > rows:
        raise ValueError("网格 (%d x %d) 密于图像 (%d x %d)" % (nx, ny, cols, rows))
    areas = [[0] * nx for _ in range(ny)]
    for ty in range(ny):
        r0 = ty * rows // ny
        r1 = (ty + 1) * rows // ny
        for tx in range(nx):
            c0 = tx * cols // nx
            c1 = (tx + 1) * cols // nx
            hit = 0
            for r in range(r0, r1):
                row = image[r]
                for c in range(c0, c1):
                    if row[c] >= threshold:
                        hit += 1
            areas[ty][tx] = hit
    return areas, rows, cols


def histogram(image, nx, ny, edges, threshold=128):
    """图块面积分桶直方图。

    返回 dict：edges/nbuckets/grid/tile_areas/bin_of/histogram/
    nonempty_buckets/tile_count/max_area。任何一块落到桶区间之外都
    抛 ValueError（桶边自身的负值/重叠由 validate_edges 先行拦截）。
    """
    nbuckets = validate_edges(edges)
    edges = list(edges)
    t0 = time.perf_counter()
    areas, rows, cols = tile_areas(image, nx, ny, threshold)
    flat = [a for row in areas for a in row]
    max_area = max(flat)
    if max_area > edges[-1] or min(flat) < edges[0]:
        raise ValueError(
            "存在图块面积落在桶区间 [%r, %r] 之外（最小 %r，最大 %r）"
            % (edges[0], edges[-1], min(flat), max_area))
    bin_of = [[_bucket_index(a, edges) for a in row] for row in areas]
    if any(b < 0 for row in bin_of for b in row):
        raise ValueError("存在图块无法落桶")
    counts = [0] * nbuckets
    for b in (b for row in bin_of for b in row):
        counts[b] += 1
    elapsed = time.perf_counter() - t0
    return {
        "edges": edges,
        "nbuckets": nbuckets,
        "grid": (nx, ny),
        "image_size": (cols, rows),
        "tile_areas": areas,
        "bin_of": bin_of,
        "histogram": counts,
        "nonempty_buckets": sum(1 for c in counts if c),
        "tile_count": nx * ny,
        "max_area": max_area,
        "elapsed_sec": elapsed,
    }


def verify_by_hand(image, nx, ny, edges, threshold=128):
    """独立逐块手算复核：不调用 histogram/tile_areas，重新切块、重新数
    像素、用显式边界比较重新落桶，并给出与直方图结果的误差上界。

    返回在手算结果之外附加 hand_histogram/max_abs_error/
    max_rel_error/error_bound/hand_elapsed_sec。
    """
    nbuckets = validate_edges(edges)
    edges = list(edges)
    result = histogram(image, nx, ny, edges, threshold)

    t0 = time.perf_counter()
    rows = len(image)
    cols = len(image[0]) if rows else 0
    hand_areas = [[0] * nx for _ in range(ny)]
    hand_bins = [[-1] * nx for _ in range(ny)]
    for ty in range(ny):
        r0 = ty * rows // ny
        r1 = (ty + 1) * rows // ny
        for tx in range(nx):
            c0 = tx * cols // nx
            c1 = (tx + 1) * cols // nx
            # 手数像素：最朴素的双重循环 + 计数器
            hit = 0
            r = r0
            while r < r1:
                c = c0
                while c < c1:
                    if image[r][c] >= threshold:
                        hit += 1
                    c += 1
                r += 1
            hand_areas[ty][tx] = hit
            # 手算落桶：逐条桶边显式比较，不借助 bisect
            b = -1
            if hit >= edges[0]:
                k = 0
                while k < nbuckets:
                    lo, hi = edges[k], edges[k + 1]
                    if k == nbuckets - 1:
                        if lo <= hit <= hi:
                            b = k
                            break
                    elif lo <= hit < hi:
                        b = k
                        break
                    k += 1
            if b < 0:
                raise ValueError(
                    "手算复核：图块 (%d,%d) 面积 %d 无法落桶" % (ty, tx, hit))
            hand_bins[ty][tx] = b
    hand_hist = [0] * nbuckets
    for b in (b for row in hand_bins for b in row):
        hand_hist[b] += 1
    hand_elapsed = time.perf_counter() - t0

    fast_areas = result["tile_areas"]
    max_abs = 0
    max_rel = 0.0
    for ty in range(ny):
        for tx in range(nx):
            a, h = fast_areas[ty][tx], hand_areas[ty][tx]
            diff = abs(a - h)
            if diff > max_abs:
                max_abs = diff
            if result["bin_of"][ty][tx] != hand_bins[ty][tx]:
                raise ValueError(
                    "手算复核：图块 (%d,%d) 落桶不一致 直方图=%d 手算=%d"
                    % (ty, tx, result["bin_of"][ty][tx], hand_bins[ty][tx]))
            denom = max(1.0, float(h))
            rel = diff / denom
            if rel > max_rel:
                max_rel = rel
    if hand_hist != result["histogram"]:
        raise ValueError(
            "手算复核：桶计数不一致 直方图=%r 手算=%r"
            % (result["histogram"], hand_hist))

    # 误差上界：观测最大绝对偏差 + 一次浮点容差（整数像素计数下实际为 0）
    eps = max(1.0, float(result["max_area"])) * sys.float_info.epsilon
    result.update({
        "hand_histogram": hand_hist,
        "hand_tile_areas": hand_areas,
        "hand_bin_of": hand_bins,
        "max_abs_error": max_abs,
        "max_rel_error": max_rel,
        "error_bound": max_abs + eps,
        "hand_elapsed_sec": hand_elapsed,
    })
    return result


def two_tier_report(image, edges, coarse=(4, 4), fine=(16, 16), threshold=128):
    """两档图块数（粗网格/细网格）各跑一遍直方图+手算复核。"""
    report = {}
    for label, grid in (("coarse", coarse), ("fine", fine)):
        nx, ny = grid
        report[label] = verify_by_hand(image, nx, ny, edges, threshold)
    return report


def default_edges(max_area):
    """按 2 的幂生成桶边，最高边严格大于 max_area，保证任何块都不溢出。"""
    m = int(max_area)
    if m < 0:
        raise ValueError("max_area 不能为负")
    # 先取 >= m 的最小 2 的幂，再上抬一档，确保最高边严格大于 m
    top = 1 << m.bit_length()
    top <<= 1
    edges = [0, 1]
    while edges[-1] < top:
        edges.append(edges[-1] * 2)
    return edges


def format_report(report):
    """把 verify_by_hand 的结果渲染成纯文本小节。"""
    lines = []
    nx, ny = report["grid"]
    lines.append("网格 %dx%d（图块 %d 个），桶数 %d，非空桶 %d"
                 % (nx, ny, report["tile_count"], report["nbuckets"],
                    report["nonempty_buckets"]))
    lines.append("  桶区间                 块数")
    for i, c in enumerate(report["histogram"]):
        lo, hi = report["edges"][i], report["edges"][i + 1]
        lines.append("  [%6g, %6g)%s   %d"
                     % (lo, hi, "]" if i == report["nbuckets"] - 1 else " ", c))
    lines.append("  直方图耗时 %.6f s，手算复核耗时 %.6f s"
                 % (report["elapsed_sec"], report["hand_elapsed_sec"]))
    lines.append("  逐块最大绝对误差 %d，最大相对误差 %.3g，误差上界 %.6g"
                 % (report["max_abs_error"], report["max_rel_error"],
                    report["error_bound"]))
    return "\n".join(lines)
