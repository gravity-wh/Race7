#!/usr/bin/env python3
"""check_waveform.py -- 按赛题 S5 判据（相关系数 > 0.9 且 MAE < 1 mV）核对波形。

与官方 verify_waveform.py 的区别：后者用"稳态区相对误差 ≤2%"，
在信号边沿/过零点会因时间步不同 + 线性插值产生伪失败。
本脚本只算赛题真正要求的两个量。

用法: python3 check_waveform.py <golden_dir> <test_dir> <golden_glob_prefix>
"""
import math
import os
import sys

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

from verify_waveform import parse_ngspice_output  # noqa: E402


def interp(pts, t):
    if not pts:
        return 0.0
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    lo, hi = 0, len(pts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pts[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, v0 = pts[lo]
    t1, v1 = pts[hi]
    if t1 == t0:
        return v0
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def stats(golden, test):
    """返回 (MAE, 最大绝对误差, Pearson r, 点数)，按信号取最差值。"""
    worst = (0.0, 0.0, 1.0, 0)
    for name, gpts in golden.items():
        if name not in test:
            continue
        tpts = test[name]
        if len(gpts) < 3:
            continue
        xs, ys = [], []
        for t, v in gpts:
            xs.append(v)
            ys.append(interp(tpts, t))
        n = len(xs)
        mae = sum(abs(a - b) for a, b in zip(xs, ys)) / n
        mx = max(abs(a - b) for a, b in zip(xs, ys))
        mx_x = sum(xs) / n
        mx_y = sum(ys) / n
        sxy = sum((a - mx_x) * (b - mx_y) for a, b in zip(xs, ys))
        sxx = sum((a - mx_x) ** 2 for a in xs)
        syy = sum((b - mx_y) ** 2 for b in ys)
        r = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 1.0
        if mae > worst[0]:
            worst = (mae, mx, r, n)
    return worst


def main():
    gdir = sys.argv[1]
    tdir = sys.argv[2]
    names = sorted(os.listdir(gdir))
    print("%-26s %10s %10s %12s %6s  %s" % ("test", "MAE(mV)", "maxabs(mV)", "r", "n", "S5"))
    npass = nfail = 0
    for fn in names:
        if not fn.endswith(".out"):
            continue
        tp = os.path.join(tdir, fn)
        if not os.path.exists(tp):
            print("%-26s  MISSING" % fn)
            continue
        try:
            g = parse_ngspice_output(os.path.join(gdir, fn))
            o = parse_ngspice_output(tp)
        except Exception as e:                      # noqa: BLE001
            print("%-26s  PARSE_ERR %s" % (fn, e))
            continue
        mae, mx, r, n = stats(g, o)
        ok = (mae * 1000.0 < 1.0) and (r > 0.9)
        npass += ok
        nfail += (not ok)
        print("%-26s %10.4f %10.4f %12.7f %6d  %s"
              % (fn, mae * 1000.0, mx * 1000.0, r, n, "PASS" if ok else "FAIL"))
    print("\nS5 判据 (r>0.9 且 MAE<1mV):  PASS=%d  FAIL=%d" % (npass, nfail))


if __name__ == "__main__":
    main()
