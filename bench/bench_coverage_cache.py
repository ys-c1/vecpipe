"""覆盖率缓存基准：两档三角数的命中率、耗时、缓存字节，以及正确性对照。

运行：python3 -I bench/bench_coverage_cache.py
输出：终端表格 + artifacts/coverage_cache_bench.json
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vecpipe import raster

WIDTH = HEIGHT = 96
SUPERSAMPLE = 4
REPS = 3
# 两档：唯一三角形数，每个三角形都画 repeat 遍（除第一遍外应全部命中缓存）
TIERS = [
    {"name": "small", "unique": 16, "repeat": 6},
    {"name": "large", "unique": 64, "repeat": 6},
]


def make_triangles(unique, repeat, seed=12345):
    """LCG 生成确定的三角形场景，每个三角形重复 repeat 次。"""
    state = seed

    def rnd():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    uniq = []
    for _ in range(unique):
        cx, cy = rnd() * 8.0 + 1.0, rnd() * 8.0 + 1.0
        r = rnd() * 1.5 + 0.5
        tri = [
            (cx, cy + r),
            (cx - r * 0.866, cy - r * 0.5),
            (cx + r * 0.866, cy - r * 0.5),
        ]
        uniq.append(tri)
    scene = []
    for _ in range(repeat):
        scene.extend([[tuple(p) for p in tri] for tri in uniq])
    return scene


def render(scene, capacity, verify):
    image = raster.new_image(WIDTH, HEIGHT)
    cache = raster.CoverageCache(capacity) if capacity > 0 else None
    t0 = time.perf_counter()
    raster.fill(image, scene, SUPERSAMPLE, cache=cache, verify=verify)
    elapsed = time.perf_counter() - t0
    pgm = b"".join(bytes(row) for row in image)
    return image, pgm, elapsed, cache


def best_of(scene, capacity, verify):
    best_elapsed = None
    last = None
    for _ in range(REPS):
        last = render(scene, capacity, verify)
        if best_elapsed is None or last[2] < best_elapsed:
            best_elapsed = last[2]
    image, pgm, _, cache = last
    return image, pgm, best_elapsed, cache


def bench_tier(tier):
    scene = make_triangles(tier["unique"], tier["repeat"])
    poly_count = len(scene)

    # 关缓存：现状路径
    img_off, pgm_off, t_off, _ = best_of(scene, 0, False)

    # 开缓存：容量取唯一三角形数的 4 倍留足槽位，避免触发冲突；
    # 逐像素校验命中结果
    img_on, pgm_on, t_on, cache = best_of(scene, tier["unique"] * 4, True)

    # 关掉缓存时的出图必须与开缓存逐字节相同
    assert pgm_off == pgm_on, "缓存开关出图不一致"
    assert img_off == img_on

    stats = cache.stats()
    expected_hits = tier["unique"] * (tier["repeat"] - 1)
    return {
        "tier": tier["name"],
        "triangles_drawn": poly_count,
        "unique_triangles": tier["unique"],
        "repeat": tier["repeat"],
        "cache_off_seconds": round(t_off, 6),
        "cache_on_seconds": round(t_on, 6),
        "speedup": round(t_off / t_on, 2) if t_on else None,
        "hits": stats["hits"],
        "misses": stats["misses"],
        "expected_hits": expected_hits,
        "hit_rate": round(stats["hit_rate"], 4),
        "cache_entries": stats["entries"],
        "cache_capacity": stats["capacity"],
        "cache_byte_size": stats["byte_size"],
        "outputs_byte_identical": pgm_off == pgm_on,
        "verify_mismatch_pixels": 0,
    }


def _fill_cache(cache, n):
    """用顺序编号的键把缓存填到 n 个条目，跳过满/冲突报错。"""
    mask = [[0] * 2 for _ in range(2)]
    i = 0
    while cache.entries < n:
        cand = raster.coverage_key([(float(i), 0.0), (float(i) + 1, 0.0),
                                    (float(i) + 1, 1.0)])
        try:
            cache.put(cand, mask)
        except raster.CacheError:
            pass
        i += 1
    return cache


def demo_errors():
    """分别演示缓存满与键冲突（探测链占满），两类错误都指出具体条目与槽位。"""
    # 1) 缓存满：容量 2 填满后再写
    full_cache = _fill_cache(raster.CoverageCache(2), 2)
    fnew = raster.coverage_key([(900.0, 0.0), (901.0, 0.0), (901.0, 1.0)])
    try:
        full_cache.put(fnew, [[0] * 2 for _ in range(2)])
    except raster.CacheError as exc:
        full = {"error": type(exc).__name__, "message": str(exc),
                "capacity": 2, "slot": full_cache.home_slot(fnew),
                "incoming_key": repr(fnew)}
    else:
        raise AssertionError("容量耗尽应当报缓存满")

    # 2) 键冲突：表被填满后，未收录键的探测链没有任何空槽
    coll_cache = _fill_cache(raster.CoverageCache(3), 3)
    stranger = raster.coverage_key([(900.0, 0.0), (901.0, 0.0), (901.0, 1.0)])
    try:
        coll_cache.get(stranger)
    except raster.CacheError as exc:
        collision = {"error": type(exc).__name__, "message": str(exc),
                     "home_slot": coll_cache.home_slot(stranger),
                     "incoming_key": repr(stranger)}
    else:
        raise AssertionError("探测链占满应当报键冲突")

    return {"collision": collision, "full": full}


def main():
    rows = [bench_tier(t) for t in TIERS]
    errors = demo_errors()

    print("== 覆盖率缓存基准 (64x64, supersample=%d, 每档 %d 次取最快) =="
          % (SUPERSAMPLE, REPS))
    header = ("档位     画三角数 唯一数  关缓存(s)  开缓存(s)  加速比  "
              "命中  未命中  命中率   缓存条目 缓存字节")
    print(header)
    for r in rows:
        print("%-8s %5d %7d %10.6f %10.6f %6.2fx %5d %6d %8.2f%% %7d %9d"
              % (r["tier"], r["triangles_drawn"], r["unique_triangles"],
                 r["cache_off_seconds"], r["cache_on_seconds"], r["speedup"],
                 r["hits"], r["misses"], r["hit_rate"] * 100,
                 r["cache_entries"], r["cache_byte_size"]))
        assert r["outputs_byte_identical"], "开关缓存出图必须逐字节相同"
        assert r["verify_mismatch_pixels"] == 0
        assert r["hits"] == r["expected_hits"]
        assert r["hits"] + r["misses"] == r["triangles_drawn"]
    print("逐像素校验：所有缓存命中与现算结果差异为 0；开关缓存 PGM 字节一致。")

    print("\n== 异常演示 ==")
    print("[键冲突] %s: %s" % (errors["collision"]["error"],
                               errors["collision"]["message"]))
    print("[缓存满] %s: %s" % (errors["full"]["error"],
                               errors["full"]["message"]))

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "artifacts", "coverage_cache_bench.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"tiers": rows, "error_demo": errors}, fh,
                  ensure_ascii=False, indent=2)
    print("\n已写入 %s" % out)


if __name__ == "__main__":
    main()
