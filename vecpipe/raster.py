"""光栅化：超采样填充、覆盖率缓存与 PGM 输出。

覆盖率缓存（CoverageCache）按多边形（三角形）坐标做键，把每个多边形
逐像素的超采样命中掩码缓存下来，相同坐标的多边形再次出现时直接复用，
不再重算 point_in_poly。键冲突与缓存满都会报错并指出条目。
"""
import sys

from .geom import point_in_poly


class CacheError(RuntimeError):
    """覆盖率缓存相关错误的基类。"""


class CacheCollisionError(CacheError):
    """不同键映射到同一槽位（键冲突）。"""

    def __init__(self, message, slot=None, stored_key=None, incoming_key=None):
        super().__init__(message)
        self.slot = slot
        self.stored_key = stored_key
        self.incoming_key = incoming_key


class CacheFullError(CacheError):
    """缓存条目数已达容量上限。"""

    def __init__(self, message, capacity=None, incoming_key=None, slot=None):
        super().__init__(message)
        self.capacity = capacity
        self.incoming_key = incoming_key
        self.slot = slot


class CacheVerifyError(CacheError):
    """缓存命中结果与现算结果逐像素对照存在非零差异。"""

    def __init__(self, message, differences=None, key=None):
        super().__init__(message)
        self.differences = differences
        self.key = key


def coverage_key(poly):
    """以多边形顶点坐标元组作为覆盖率缓存键。

    坐标完全相同（浮点逐位相等）的多边形视为同一几何，命中同一覆盖率。
    """
    return tuple((float(x), float(y)) for x, y in poly)


def key_hash(key):
    """确定性 FNV-1a 哈希；只依赖数值，跨进程稳定，不受 PYTHONHASHSEED 影响。"""
    h = 0xCBF29CE484222325
    for x, y in key:
        for part in (x, y):
            for byte in repr(part).encode("utf-8"):
                h ^= byte
                h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def _deep_sizeof(obj, seen):
    """递归估算 CPython 对象实际占用字节（含容器与内部 int/列表的分配）。"""
    oid = id(obj)
    if oid in seen:
        return 0
    seen.add(oid)
    total = sys.getsizeof(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            total += _deep_sizeof(k, seen) + _deep_sizeof(v, seen)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            total += _deep_sizeof(item, seen)
    return total


class CoverageCache:
    """定容开放寻址缓存：键 -> 逐像素超采样命中掩码（二维 int 列表）。

    键的归属槽位为 hash(key) % capacity；该槽被别的键占用时线性探测
    下一个空槽。只有探测链上的槽位全部被其他条目占满（结构性键冲突）
    或表中条目数达到 capacity（缓存满）时才报错，两类错误都带条目与
    槽位详情。capacity<=0 表示关闭缓存。
    """

    def __init__(self, capacity):
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise TypeError("capacity 必须是整数")
        if capacity < 0:
            raise ValueError("capacity 不能为负")
        self.capacity = capacity
        self._slots = [None] * capacity
        self._entries = 0
        self.hits = 0
        self.misses = 0
        self.collisions = 0

    @property
    def enabled(self):
        return self.capacity > 0

    @property
    def entries(self):
        return self._entries

    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0

    @property
    def byte_size(self):
        """缓存当前占用字节（含槽位数组、键、掩码及其内部 int/列表）。"""
        return _deep_sizeof(self._slots, set())

    def home_slot(self, key):
        """键的归属（主）槽位。"""
        return key_hash(key) % self.capacity

    def slot_of(self, key):
        """键实际所在槽位；不存在时返回其主槽位。"""
        home = self.home_slot(key)
        for step in range(self.capacity):
            slot = (home + step) % self.capacity
            entry = self._slots[slot]
            if entry is None:
                return home
            if entry[0] == key:
                return slot
        return home

    def _probe(self, key):
        """沿探测链查找，返回 (entry_or_None, 途经占用槽列表)。"""
        home = self.home_slot(key)
        occupied = []
        for step in range(self.capacity):
            slot = (home + step) % self.capacity
            entry = self._slots[slot]
            if entry is None:
                return None, occupied
            occupied.append((slot, entry))
            if entry[0] == key:
                return entry, occupied
        return None, occupied

    def get(self, key):
        """命中返回掩码并累计 hits；未命中累计 misses 并返回 None。"""
        entry, occupied = self._probe(key)
        if entry is not None:
            self.hits += 1
            return entry[1]
        # 探测链被其他键占满且没有空槽：结构性键冲突
        if occupied and len(occupied) == self.capacity:
            self.collisions += 1
            raise CacheCollisionError(
                "覆盖率缓存键冲突：条目 %r 的探测链（主槽 %d 起）被其他条目占满，"
                "无法读取，链上首个条目 %r 位于槽位 %d"
                % (key, self.home_slot(key), occupied[0][1][0], occupied[0][0]),
                slot=occupied[0][0],
                stored_key=occupied[0][1][0], incoming_key=key,
            )
        self.misses += 1
        return None

    def put(self, key, mask):
        home = self.home_slot(key)
        # 先判满：表满时探测链上不存在空槽，不先判满会被误报成键冲突
        if self._entries >= self.capacity:
            raise CacheFullError(
                "覆盖率缓存已满：容量 %d，无法写入条目 %r（主槽位 %d）"
                % (self.capacity, key, home),
                capacity=self.capacity, incoming_key=key, slot=home,
            )
        for step in range(self.capacity):
            slot = (home + step) % self.capacity
            entry = self._slots[slot]
            if entry is not None and entry[0] == key:
                return
            if entry is None:
                if step > 0:
                    self.collisions += 1
                self._slots[slot] = (key, mask)
                self._entries += 1
                return
        # 探测链上没有空槽也没有同键条目：结构性键冲突
        self.collisions += 1
        raise CacheCollisionError(
            "覆盖率缓存键冲突：条目 %r 的探测链（主槽 %d 起）被其他条目占满，"
            "无法写入，链上首个条目 %r 位于槽位 %d"
            % (key, home, self._slots[home][0], home),
            slot=home, stored_key=self._slots[home][0], incoming_key=key,
        )

    def stats(self):
        return {
            "capacity": self.capacity,
            "entries": self._entries,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hit_rate,
            "collisions": self.collisions,
            "byte_size": self.byte_size,
        }


def new_image(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("画幅必须为正")
    return [[0] * width for _ in range(height)]


def bounds(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def fill(image, polygons, supersample=1, cache=None, verify=False):
    """超采样填充。

    cache 为 None 或容量 0 时走原始逐像素路径，出图与启用缓存前逐字节相同。
    cache 为 CoverageCache 时按多边形坐标缓存逐像素命中掩码；verify=True 时
    每次命中都现算一遍并与缓存逐像素对照，存在差异即抛 CacheVerifyError。
    """
    if supersample < 1:
        raise ValueError("supersample 必须为正")
    height = len(image)
    width = len(image[0]) if height else 0
    for poly in polygons:
        if len(poly) < 3:
            raise ValueError("多边形至少三个顶点")
    xs = [p[0] for poly in polygons for p in poly]
    ys = [p[1] for poly in polygons for p in poly]
    if not xs:
        return image
    if cache is None or not cache.enabled:
        return _fill_direct(image, polygons, supersample, xs, ys, width, height)
    return _fill_cached(image, polygons, supersample, xs, ys, width, height,
                        cache, verify)


def _fill_direct(image, polygons, supersample, xs, ys, width, height):
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    spanx = (maxx - minx) or 1.0
    spany = (maxy - miny) or 1.0
    for row in range(height):
        for col in range(width):
            hit = 0
            for sj in range(supersample):
                for si in range(supersample):
                    px = minx + (col + (si + 0.5) / supersample) * spanx / width
                    py = miny + (row + (sj + 0.5) / supersample) * spany / height
                    for poly in polygons:
                        if point_in_poly(poly, px, py):
                            hit += 1
                            break
            image[row][col] = int(255 * hit / (supersample * supersample))
    return image


def _fill_cached(image, polygons, supersample, xs, ys, width, height,
                 cache, verify):
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    spanx = (maxx - minx) or 1.0
    spany = (maxy - miny) or 1.0
    total = supersample * supersample
    union = [[0] * width for _ in range(height)]
    for poly in polygons:
        key = coverage_key(poly)
        tile = cache.get(key)
        if tile is None:
            tile = _triangle_tile(poly, width, height, supersample,
                                  minx, miny, spanx, spany)
            cache.put(key, tile)
        elif verify:
            fresh = _triangle_tile(poly, width, height, supersample,
                                   minx, miny, spanx, spany)
            r0, c0, mask = tile
            fr0, fc0, fmask = fresh
            if (r0, c0) != (fr0, fc0) or len(mask) != len(fmask) \
                    or len(mask[0]) != len(fmask[0]):
                raise CacheVerifyError(
                    "覆盖率缓存校验失败：键 %r 的包围盒与现算结果不一致："
                    "cached=(r0=%d,c0=%d,size=%dx%d) fresh=(r0=%d,c0=%d,size=%dx%d)"
                    % (key, r0, c0, len(mask), len(mask[0]),
                       fr0, fc0, len(fmask), len(fmask[0])),
                    differences=[(tile, fresh)], key=key,
                )
            diffs = [(r0 + dr, c0 + dc, mask[dr][dc], fmask[dr][dc])
                     for dr in range(len(mask))
                     for dc in range(len(mask[0]))
                     if mask[dr][dc] != fmask[dr][dc]]
            if diffs:
                raise CacheVerifyError(
                    "覆盖率缓存校验失败：键 %r 有 %d 个像素与现算结果不一致，"
                    "首个差异 (row,col,cached,fresh)=%s"
                    % (key, len(diffs), diffs[0]),
                    differences=diffs, key=key,
                )
        r0, c0, mask = tile
        for dr, mrow in enumerate(mask):
            urow = union[r0 + dr]
            for dc, bits in enumerate(mrow):
                urow[c0 + dc] |= bits
    for row in range(height):
        for col in range(width):
            image[row][col] = int(255 * (bin(union[row][col]).count("1")) / total)
    return image


def _triangle_tile(poly, width, height, supersample, minx, miny, spanx, spany):
    """单个多边形的稀疏覆盖率块：(起始行, 起始列, 包围盒内逐像素命中掩码)。

    只计算多边形包围盒覆盖到的像素，掩码第 k 位表示该像素第 k 个采样点
    是否落在多边形内；包围盒外的像素覆盖率恒为 0，不存储。
    """
    pminx, pminy, pmaxx, pmaxy = bounds(poly)
    c0 = max(0, int((pminx - minx) / spanx * width))
    c1 = min(width - 1, int((pmaxx - minx) / spanx * width))
    r0 = max(0, int((pminy - miny) / spany * height))
    r1 = min(height - 1, int((pmaxy - miny) / spany * height))
    mask = [[0] * (c1 - c0 + 1) for _ in range(r1 - r0 + 1)]
    for dr in range(r1 - r0 + 1):
        row = r0 + dr
        mrow = mask[dr]
        for dc in range(c1 - c0 + 1):
            col = c0 + dc
            bits = 0
            bit = 1
            for sj in range(supersample):
                for si in range(supersample):
                    px = minx + (col + (si + 0.5) / supersample) * spanx / width
                    py = miny + (row + (sj + 0.5) / supersample) * spany / height
                    if point_in_poly(poly, px, py):
                        bits |= bit
                    bit <<= 1
            mrow[dc] = bits
    return r0, c0, mask


def save_pgm(path, image):
    height = len(image)
    width = len(image[0]) if height else 0
    if width == 0 or height == 0:
        raise ValueError("空图不能导出")
    with open(path, "wb") as fh:
        fh.write(("P5\n%d %d\n255\n" % (width, height)).encode("ascii"))
        for row in image:
            fh.write(bytes(row))


def count_on(image, threshold=128):
    return sum(1 for row in image for v in row if v >= threshold)
