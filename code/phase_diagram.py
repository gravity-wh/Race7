"""phase_diagram.py -- (κ, s) 相图：哪个精度档在给定硬件上最优

代价模型（FP64 等价 flops）:
    T(u) = (2/3)n^3 / s_u  +  k(u,κ) * 4 n^2
    S(u) = (2/3)n^3 / T(u)

s_64 = 1, s_32 = s, s_11 = 4s（张量核相对 FP32 取 4×）
k(u,κ) 用实测的 GMRES-IR 迭代数插值。
"""
import csv
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "figures")
RES = os.path.join(ROOT, "results")

# 实测迭代数（外+内，n=64，results/scan.csv 的中位）
K32 = [(1e6, 7), (1e8, 13), (1e9, 37), (1e10, 53), (1e12, 83), (1e14, 107)]
K11 = [(1e6, 86), (1e8, 123), (1e9, 131), (1e10, 131), (1e12, 131), (1e14, 131)]
KMAX32, KMAX11, KMAX64 = 1e14, 1e14, 1e18

# 11 位的吞吐比：默认用 Mars X201 实测的 s16（半精度存储，无 MMA）
S11 = float(os.environ.get("S11", "2.339"))


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


def best(n, kappa, s):
    """返回 (最优精度标签, 加速比, 三档加速比)"""
    L = (2.0 / 3.0) * n ** 3
    cand = []
    cand.append(("FP64", 1.0, 0))
    if kappa <= KMAX32:
        k = interp(K32, kappa)
        cand.append(("FP32", L / (L / s + k * 4.0 * n * n), k))
    if kappa <= KMAX11:
        k = interp(K11, kappa)
        cand.append(("11-bit", L / (L / S11 + k * 4.0 * n * n), k))
    lab, sp, _ = max(cand, key=lambda t: t[1])
    return lab, sp, cand


COLORS = {"FP64": "#cbd5e1", "FP32": "#2563eb", "11-bit": "#d97706"}


def svg_heatmap(path, n, kappas, svals):
    W, H = 720, 400
    ml, mr, mt, mb = 82, 200, 48, 62
    L, R = ml, W - mr
    T, B = mt, H - mb
    lx0, lx1 = math.log10(kappas[0]), math.log10(kappas[-1])
    ly0, ly1 = math.log10(svals[0]), math.log10(svals[-1])
    cw = (R - L) / len(kappas)
    ch = (B - T) / len(svals)

    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d"'
         ' font-family="\'Noto Sans SC\',sans-serif">' % (W, H, W, H),
         '<rect width="100%" height="100%" fill="#fff"/>',
         '<text x="%d" y="26" font-size="15" font-weight="600" fill="#0f172a">'
         '(κ, s) 相图：n=%d，s₃₂ 为横轴变量，s₁₁=%.2f（实测）</text>' % (L, n, S11)]
    rows = []
    for j, s in enumerate(svals):
        y = B - (j + 1) * ch
        for i, kap in enumerate(kappas):
            lab, sp, _ = best(n, kap, s)
            x = L + i * cw
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" '
                     'stroke="#fff" stroke-width="0.6"/>'
                     % (x, y, cw + 0.5, ch + 0.5, COLORS[lab]))
            rows.append((n, kap, s, lab, sp))
    for i, kap in enumerate(kappas):
        if i % 2 == 0:
            o.append('<text x="%.1f" y="%d" font-size="11" fill="#475569" text-anchor="middle">'
                     '%.0e</text>' % (L + (i + 0.5) * cw, B + 18, kap))
    for j, s in enumerate(svals):
        if j % 2 == 0:
            o.append('<text x="%d" y="%.1f" font-size="11" fill="#475569" text-anchor="end">'
                     '%.1f</text>' % (L - 8, B - (j + 0.5) * ch + 4, s))
    o.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#94a3b8"/>'
             % (L, T, R - L, B - T))
    o.append('<text x="%.1f" y="%d" font-size="13" fill="#334155" text-anchor="middle">'
             'κ₂(A)</text>' % ((L + R) / 2, B + 44))
    o.append('<text x="20" y="%.1f" font-size="13" fill="#334155" text-anchor="middle" '
             'transform="rotate(-90 20 %.1f)">s = FP32/FP64 吞吐比</text>'
             % ((T + B) / 2, (T + B) / 2))
    # 图例
    ly = T + 20
    for lab in ("FP32", "11-bit", "FP64"):
        o.append('<rect x="%d" y="%d" width="18" height="14" fill="%s"/>'
                 % (R + 18, ly - 11, COLORS[lab]))
        o.append('<text x="%d" y="%d" font-size="12" fill="#334155">%s 最优</text>'
                 % (R + 42, ly, lab))
        ly += 24
    o.append('<text x="%d" y="%d" font-size="11" fill="#64748b">s=2：CPU 实测</text>'
             % (R + 18, T + 110))
    o.append("</svg>")
    open(path, "w").write("\n".join(o))
    return rows


def main():
    kappas = [10 ** (3 + 0.5 * i) for i in range(13)]      # 1e3 .. 1e9
    kappas += [1e10, 1e11, 1e12, 1e13, 1e14]
    kappas = sorted(kappas)
    svals = [2 ** (0.5 * i) for i in range(11)]            # 1 .. 32
    allrows = []
    for n in (1024, 4096, 16384):
        rows = svg_heatmap(os.path.join(FIG, "fig9_phase_n%d.svg" % n), n, kappas, svals)
        allrows += rows
    with open(os.path.join(RES, "phase_diagram.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "kappa", "s", "best", "speedup"])
        w.writerows(allrows)
    # 交叉点：11-bit 首次超过 FP32 的 n
    print("n, κ, s  -> 交叉点 n*")
    for kappa in (1e6, 1e8, 1e10, 1e12):
        for s in (2, 4, 8):
            lo, hi = 64, 65536
            for _ in range(40):
                mid = math.sqrt(lo * hi)
                if best(mid, kappa, s)[0] == "11-bit":
                    hi = mid
                else:
                    lo = mid
            print("  κ=%.0e s=%d -> n*≈%.0f" % (kappa, s, hi))


if __name__ == "__main__":
    main()
