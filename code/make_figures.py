"""make_figures.py -- 从 scan.csv / reg.csv 生成报告用图与汇总表"""
import csv
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svgplot import Panel, HBar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
FIG = os.path.join(ROOT, "figures")


def load(name):
    with open(os.path.join(RES, name)) as f:
        return list(csv.DictReader(f))


def med(rows, key):
    v = [float(r[key]) for r in rows if r[key] not in ("", "inf", "-inf")]
    return statistics.median(v) if v else float("nan")


SCAN = load("scan.csv")
REG = load("reg.csv")
KS = sorted({float(r["kappa2"]) for r in SCAN
             if r["family"] == "kappa" and r["n"] == "64"})


def rows_of(v, k):
    return [r for r in SCAN if r["family"] == "kappa" and r["n"] == "64"
            and r["variant"] == v and abs(float(r["kappa2"]) - k) <= 1e-9 * max(k, 1)]


def success(v, k, tol=10.0):
    g = rows_of(v, k)
    if not g:
        return 0.0
    return sum(1 for r in g if float(r["ratio"]) <= tol) / len(g)


def kappa_max(v, tol=10.0, need=0.6):
    best = None
    for k in KS:
        if success(v, k, tol) >= need:
            best = k
    return best


# ------------------------------------------------------------- fig 1 --------
ROWS = [
    ("纯 FP32 求解（无精化）",        "fp32",        0, "#94a3b8"),
    ("11 位下分解 + 定常 IR",         "tf32_ir",     1, "#d97706"),
    ("FP64 分解 → 因子存 11 位 + IR", "q11_ir",      1, "#d97706"),
    ("FP32 分解 + 定常 IR",           "fp32_ir",     0, "#2563eb"),
    ("FP32 分解 + FP32 求解 + IR",    "fp32_ir_s32", 0, "#2563eb"),
    ("因子存 11 位 + GMRES-IR",       "q11_gir",     1, "#d97706"),
    ("FP64 分解 → 因子存 FP32 + IR",  "q24_ir",      0, "#0891b2"),
    ("11 位下分解 + GMRES-IR",        "tf32_gir",    1, "#d97706"),
    ("FP32 分解 + GMRES-IR",          "fp32_gir",    0, "#2563eb"),
]
rows = []
for lab, v, _, color in ROWS:
    km = kappa_max(v) or 1.0
    open_end = abs(km - KS[-1]) < 1e-9
    rows.append((lab, math.log10(km), color, open_end))
rows.sort(key=lambda r: -r[1])
HBar(rows, ml=292, title="能力边界：仍能把前向误差压回 FP64 水平的最高条件数（n=64，5 seeds，≥60% 成功）",
     xlabel="κ₂(A) 上限").save(os.path.join(FIG, "fig1_envelope.svg"))

# ------------------------------------------------------------- fig 2 --------
p = Panel(title="前向误差的断崖：低精度配置在越过边界后不再收敛（n=64，5 seeds 中位）",
          xlabel="κ₂(A)", ylabel="前向相对误差 FE", xlog=True, ylog=True,
          ylim=(1e-18, 1e2),
          yticks=[1e-16, 1e-12, 1e-8, 1e-4, 1e0])
p.plot([1e0, 1e18], [1e0 * 1.1e-16, 1e18 * 1.1e-16], label="FP64 极限 ≈ κ·u",
       color="#cbd5e1", dash="6,4", width=1.8)
for v, lab, dash in [("fp32_ir", "FP32 分解 + 定常 IR", None),
                     ("q11_ir", "因子存 11 位 + 定常 IR", "2,3"),
                     ("q11_gir", "因子存 11 位 + GMRES-IR", "5,3"),
                     ("tf32_ir", "11 位下分解 + 定常 IR", "4,2"),
                     ("tf32_gir", "11 位下分解 + GMRES-IR", "1,2"),
                     ("fp32_gir", "FP32 分解 + GMRES-IR", None),
                     ("q24_ir", "因子存 FP32 + 定常 IR", "2,3")]:
    xs, ys = [], []
    for k in KS:
        g = rows_of(v, k)
        if not g:
            continue
        r = med(g, "ferr")
        xs.append(k)
        ys.append(min(r, 1e2))
        if r > 1e2:
            break
    p.plot(xs, ys, label=lab, dash=dash)
p.save(os.path.join(FIG, "fig2_cliff.svg"))

# ------------------------------------------------------------- fig 3 --------
p = Panel(title="精化迭代步数（外层 + 内层）vs 条件数，n=64",
          xlabel="κ₂(A)", ylabel="迭代步数", xlog=True, ylim=(0, 160),
          yticks=[0, 20, 40, 60, 80, 100, 120, 140, 160])
for v, lab, dash in [("fp32_ir", "FP32 分解 + 定常 IR", None),
                     ("fp32_gir", "FP32 分解 + GMRES-IR", None),
                     ("q11_gir", "因子存 11 位 + GMRES-IR", "5,3"),
                     ("tf32_gir", "11 位下分解 + GMRES-IR", "1,2")]:
    xs, ys = [], []
    for k in KS:
        g = rows_of(v, k)
        if not g or med(g, "ratio") > 1e3:
            continue
        xs.append(k)
        ys.append(med(g, "iters") + med(g, "inner"))
    p.plot(xs, ys, label=lab, dash=dash)
p.save(os.path.join(FIG, "fig3_iterations.svg"))

# ------------------------------------------------------------- fig 4 --------
p = Panel(title="“量化即正则化”：低精度分解使 ‖M⁻¹‖ 在 κ 增大时饱和（n=48）",
          xlabel="κ₂(A)", ylabel="‖M⁻¹‖₂ 估计", xlog=True, ylog=True)
p.plot([1e3, 1e14], [1e3 / 0.2, 1e14 / 0.2], label="参考：κ/‖A‖（无正则化）",
       color="#cbd5e1", dash="6,4", width=1.8)
for uf, lab, dash in [(53, "FP64 分解", None), (24, "FP32 分解", None),
                      (11, "11 位分解", "5,3")]:
    d = sorted((float(r["kappa"]), float(r["invnorm"]))
               for r in REG if int(r["u_f"]) == uf)
    p.plot([a for a, _ in d], [b for _, b in d], label=lab, dash=dash)
p.save(os.path.join(FIG, "fig4_regularization.svg"))

# ------------------------------------------------------------- fig 5 --------
p = Panel(title="预条件算子偏差 ‖A M⁻¹ − I‖：低精度下被封顶而非随 κ 线性增长（n=48）",
          xlabel="κ₂(A)", ylabel="‖A M⁻¹ − I‖_F", xlog=True, ylog=True)
for uf, lab, dash in [(53, "FP64 分解", None), (24, "FP32 分解", None),
                      (11, "11 位分解", "5,3")]:
    d = sorted((float(r["kappa"]), float(r["precond_dev"]))
               for r in REG if int(r["u_f"]) == uf)
    p.plot([a for a, _ in d], [b for _, b in d], label=lab, dash=dash)
p.save(os.path.join(FIG, "fig5_precond_dev.svg"))

# ------------------------------------------------------------- fig 6 --------
def inner_iters(k):
    pts = []
    for kk in KS:
        g = rows_of("fp32_gir", kk)
        if g and med(g, "ratio") < 1e3:
            pts.append((math.log10(kk), med(g, "iters") + med(g, "inner")))
    if not pts:
        return 8.0
    x = math.log10(k)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


ns = [128, 256, 512, 1024, 2048, 4096, 8192]
p = Panel(title="端到端加速比 vs 矩阵阶数（相对纯 FP64 求解；含精化开销）",
          xlabel="n", ylabel="相对加速比", xlog=True, ylim=(0, 8.4),
          yticks=[0, 1, 2, 3, 4, 5, 6, 7, 8],
          xticks=[128, 256, 512, 1024, 2048, 4096, 8192])
for kap, lab, dash in [(1e4, "κ=1e4", None), (1e8, "κ=1e8", "5,3"),
                       (1e12, "κ=1e12", "1,2")]:
    it = inner_iters(kap)
    ys = [(2.0 / 3.0 * n ** 3) / ((2.0 / 3.0) * n ** 3 / 2.0 + it * 4.0 * n ** 2) for n in ns]
    p.plot(ns, ys, label=lab + "（FP32 分解）", dash=dash)
it = inner_iters(1e12)
ys = [(2.0 / 3.0 * n ** 3) / ((2.0 / 3.0) * n ** 3 / 8.0 + it * 4.0 * n ** 2) for n in ns]
p.plot(ns, ys, label="κ=1e12（11 位分解）", color="#94a3b8", dash="2,3")
p.hline(2.0, label="FP32 上限 2×", color="#cbd5e1")
p.save(os.path.join(FIG, "fig6_speedup.svg"))

# ------------------------------------------------------------- fig 7/8 ----
REG2 = load("reg2.csv")


def series(mode, uf, col):
    d = sorted((float(r["kappa"]), float(r[col])) for r in REG2
               if r["mode"] == mode and int(r["u_f"]) == uf)
    return [a for a, _ in d], [b for _, b in d]


p = Panel(title="同一 u_q 下：“压缩 FP64 因子” vs “在 u_q 下重算”——‖M⁻¹‖",
          xlabel="κ₂(A)", ylabel="‖M⁻¹‖₂ 估计", xlog=True, ylog=True)
p.plot(*series("fp64", 53, "invnorm"), label="FP64 因子（参考）", color="#cbd5e1", dash="6,4", width=1.8)
for uf, st in ((24, None), (11, "5,3")):
    p.plot(*series("compress", uf, "invnorm"), label="%d 位：压缩 FP64 因子" % uf, dash=st)
    p.plot(*series("recompute", uf, "invnorm"), label="%d 位：重算" % uf, dash="2,3")
p.save(os.path.join(FIG, "fig7_compress_vs_recompute.svg"))

p = Panel(title="同一 u_q 下：预条件偏差 ‖A M⁻¹ − I‖ 的两种命运",
          xlabel="κ₂(A)", ylabel="‖A M⁻¹ − I‖_F", xlog=True, ylog=True)
p.plot(*series("fp64", 53, "precond"), label="FP64 因子（参考）", color="#cbd5e1", dash="6,4", width=1.8)
for uf, st in ((24, None), (11, "5,3")):
    p.plot(*series("compress", uf, "precond"), label="%d 位：压缩（随 κ 发散）" % uf, dash=st)
    p.plot(*series("recompute", uf, "precond"), label="%d 位：重算（被封顶）" % uf, dash="2,3")
p.save(os.path.join(FIG, "fig8_dev_vs_kappa.svg"))

# ------------------------------------------------------------- 汇总表 ------
lines = ["# 自动汇总（由 results/scan.csv 生成）", "",
         "## 表 A：前向误差比中位数（FE / FE_FP64），n=64，5 seeds", "",
         "| 配置 | " + " | ".join("%.0e" % k for k in KS) + " |",
         "|---|" + "---|" * len(KS)]
for v in ["fp32", "fp32_ir", "fp32_ir_s32", "fp32_gir", "q24_ir", "q24_gir",
          "q11_ir", "q11_gir", "tf32_ir", "tf32_gir"]:
    cells = []
    for k in KS:
        g = rows_of(v, k)
        r = med(g, "ratio") if g else float("nan")
        cells.append("—" if math.isnan(r) else ("%.1e" % r))
    lines.append("| %s | %s |" % (v, " | ".join(cells)))

lines += ["", "## 表 B：迭代步数中位数（外层 + 内层），n=64", "",
          "| 配置 | " + " | ".join("%.0e" % k for k in KS) + " |",
          "|---|" + "---|" * len(KS)]
for v in ["fp32_ir", "fp32_gir", "q11_ir", "q11_gir", "tf32_gir"]:
    cells = []
    for k in KS:
        g = rows_of(v, k)
        it = med(g, "iters") + med(g, "inner") if g else float("nan")
        cells.append("—" if math.isnan(it) else "%.0f" % it)
    lines.append("| %s | %s |" % (v, " | ".join(cells)))

with open(os.path.join(RES, "summary.md"), "w") as f:
    f.write("\n".join(lines) + "\n")
print("figures + summary.md written")
