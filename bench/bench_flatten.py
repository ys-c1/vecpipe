"""自适应细分基准：两档曲率下段数、耗时与弦高误差对照。

用法：python3 bench/bench_flatten.py
对照基准：4096 段均匀采样的参考折线（残余误差 O(4096^-4)，可忽略）。
"""
import os
import sys
import timeit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vecpipe import geom

# 两档曲率：缓弯（长而平）与急弯（控制点大幅摆动）
CURVES = [
    ("缓弯 gentle", ((0, 0), (4, 0.2), (8, 0.2), (12, 0))),
    ("急弯 tight ", ((1.5, -2.25), (7.0, 0.5), (-3.25, 4.0), (9.75, 8.125))),
]
TOLERANCES = (0.25, 0.05)
REF_SEGMENTS = 4096
REPEAT = 200


def measure(curve, tol):
    leaves = geom.adaptive_leaves(*curve, tol)
    poly = geom.adaptive_flatten(*curve, tol)
    segments = len(leaves)
    measured = geom.max_chord_error(*curve, poly, REF_SEGMENTS)
    bound = geom.adaptive_error_bound(*curve, tol)
    elapsed = timeit.timeit(
        lambda: geom.adaptive_flatten(*curve, tol), number=REPEAT) / REPEAT
    ok = measured <= bound <= tol
    return segments, elapsed, measured, bound, ok


def measure_fixed(curve, segments):
    poly = geom.flatten(*curve, segments)
    measured = geom.max_chord_error(*curve, poly, REF_SEGMENTS)
    elapsed = timeit.timeit(
        lambda: geom.flatten(*curve, segments), number=REPEAT) / REPEAT
    return elapsed, measured


def main():
    header = "%-12s %-18s %6s %10s %12s %12s %6s" % (
        "曲线", "模式", "段数", "耗时[us]", "实测最大误差", "解析上界", "达标")
    print(header)
    print("-" * len(header))
    all_ok = True
    for name, curve in CURVES:
        for tol in TOLERANCES:
            n, elapsed, measured, bound, ok = measure(curve, tol)
            all_ok &= ok
            print("%-12s adaptive tol=%-5s %6d %10.2f %12.6f %12.6f %6s"
                  % (name, tol, n, elapsed * 1e6, measured, bound,
                     "是" if ok else "否"))
        # 固定 16 段基线：与改造前逐字节相同的路径
        elapsed, measured = measure_fixed(curve, 16)
        print("%-12s fixed    16       %6d %10.2f %12.6f %12s %6s"
              % (name, 16, elapsed * 1e6, measured, "-", "-"))
        print()
    print("参考折线：每条曲线 %d 段均匀采样；每种模式计时取 %d 次均值"
          % (REF_SEGMENTS, REPEAT))
    print("结论：%s" % ("所有容差下 实测误差 <= 解析上界 <= 容差"
                     if all_ok else "存在超差！"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
