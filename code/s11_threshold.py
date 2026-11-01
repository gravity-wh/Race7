"""s11_threshold.py -- 11 位档的"实现门槛" s11*(κ,n)

11 位优于 FP32 的充要条件（FP64 等价代价）：
    L/s11 + 4 k11 n^2  <  L/s32 + 4 k32 n^2 ,   L = (2/3) n^3
=>  1/s11 < 1/s32 - 6 Δk / n        (Δk = k11 - k32)
=>  s11 > s11* = 1 / (1/s32 - 6 Δk / n) ,   有解当且仅当 n > 6 s32 Δk

输出 figures/fig10_s11_threshold.svg 与 results/s11_threshold.csv
"""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgplot import Panel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "figures")
RES = os.path.join(ROOT, "results")

S32 = 1.008          # hcBLAS 稠密 GEMM 实测（FP32/FP64 同速）
S16 = 2.339          # 朴素内核的 half/double 比（内存受限，非算力）

K32 = [(1e6, 7), (1e8, 13), (1e9, 37), (1e10, 53), (1e12, 83)]
K11 = [(1e6, 86), (1e8, 123), (1e9, 131), (1e10, 131), (1e12, 131)]


def interp(pts, k):
    x = math.log10(k)
    if x <= math.log10(pts[0][0]):
        return pts[0][1]
    if x >= math.log10(pts[-1][0]):
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        a, b = math.log10(x0), math.log10(x1)
        if a <= x <= b:
            return y0 + (y1 - y0) * (x - a) / (b - a)
    return pts[-1][1]


def s11_star(kappa, n):
    dk = interp(K11, kappa) - interp(K32, kappa)
    denom = 1.0 / S32 - 6.0 * dk / n
    if denom <= 1e-12:
        return float("inf")          # 该 n 下 11 位永远追不上
    return 1.0 / denom


def main():
    ns = [256 * 2 ** i for i in range(9)]      # 256 .. 65536
    kappas = [1e6, 1e8, 1e10, 1e12]

    p = Panel(title="11 位档的实现门槛 s₁₁*(κ,n)：低于此线才划算（Mars X201）",
              xlabel="n", ylabel="所需 s₁₁（11 位/FP64 吞吐比）",
              xlog=True, ylog=True, ylim=(0.95, 9.5), yticks=[1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 8.0])
    p.plot([ns[0], ns[-1]], [S32, S32],
           label="FP32 实测 s₃₂ = 2.29（基线）", color="#94a3b8", dash="6,4", width=2.0)
    p.plot([ns[0], ns[-1]], [S16, S16],
           label="半精度存储实测 s₁₆ = 2.34（无 MMA）", color="#dc2626", dash="2,3", width=2.0)
    p.plot([ns[0], ns[-1]], [8.0, 8.0],
           label="MMA 典型下界 8×", color="#059669", dash="1,2", width=1.6)
    for k in kappas:
        xs, ys = [], []
        for n in ns:
            v = s11_star(k, n)
            if math.isfinite(v) and v <= 9.0:
                xs.append(n)
                ys.append(max(v, 0.95))
        p.plot(xs, ys, label="κ=%.0e" % k, marker="s", width=2.2)
    p.save(os.path.join(FIG, "fig10_s11_threshold.svg"))

    with open(os.path.join(RES, "s11_threshold.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kappa", "n", "s11_star", "amortize_threshold"])
        for k in kappas:
            dk = interp(K11, k) - interp(K32, k)
            for n in ns:
                w.writerow([k, n, "%.3f" % s11_star(k, n), "%.0f" % (6 * S32 * dk)])

    print("κ        Δk    n 门槛     s11*(n=1024)  s11*(4096)  s11*(16384)")
    for k in kappas:
        dk = interp(K11, k) - interp(K32, k)
        row = ["%.0e" % k, "%4.0f" % dk, "%8.0f" % (6 * S32 * dk)]
        for n in (1024, 4096, 16384):
            v = s11_star(k, n)
            row.append("%10.2f" % v if math.isfinite(v) else "     never")
        print("  ".join(row))


if __name__ == "__main__":
    main()
