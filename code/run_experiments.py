"""run_experiments.py -- 混合精度 LU + 精化 的可行域扫描

输出: results/scan.csv
用法: python3 run_experiments.py [--quick] [--seeds 5]
"""
import argparse
import csv
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplib as M

R64 = M.rounder(53)
R32 = M.rounder(24)
R11 = M.rounder(11)

# 相对 FP64 的吞吐倍率（H100 量级：FP64 34 / FP32 67 / TF32 495 TFLOPS）
SPEED = {53: 1.0, 24: 2.0, 11: 8.0}

# name, factor_p, store_p, solve_p, kind
VARIANTS = [
    ("fp64",       53, 53, 53, "none"),
    ("fp32",       24, 24, 53, "none"),
    ("fp32_ir",    24, 24, 53, "ir"),
    ("fp32_ir_s32", 24, 24, 24, "ir"),
    ("fp32_gir",   24, 24, 53, "gir"),
    ("q24_ir",     53, 24, 53, "ir"),
    ("q24_gir",    53, 24, 53, "gir"),
    ("q11_ir",     53, 11, 53, "ir"),
    ("q11_gir",    53, 11, 53, "gir"),
    ("tf32_ir",    11, 11, 53, "ir"),
    ("tf32_gir",   11, 11, 53, "gir"),
]


def quantize_factors(LU, p):
    r = M.rounder(p)
    return [[r(v) for v in row] for row in LU]


def run_one(args):
    fam, n, seed, kappa_target = args
    t0 = time.time()
    if fam == "kappa":
        A, kap2 = M.make_kappa_matrix(n, kappa_target, seed=seed)
    elif fam == "laplace2d":
        A = M.make_laplacian_2d(int(round(math.sqrt(n))))
        kap2 = float("nan")
    elif fam == "laplace1d":
        A = M.make_laplacian_1d(n)
        kap2 = float("nan")
    elif fam == "diagdom":
        A = M.make_diag_dominant(n, seed=seed)
        kap2 = float("nan")
    elif fam == "circuit":
        A = M.make_sparse_circuit(n, seed=seed)
        kap2 = float("nan")
    elif fam == "wilkinson":
        A = M.make_wilkinson(n)
        kap2 = float("nan")
    else:
        raise ValueError(fam)

    rng = M.RNG(1000 + seed)
    xt = [rng.gauss() for _ in range(n)]
    b = M.matvec(A, xt)

    LU64, piv64, g64 = M.lu_factor(A, R64)
    LU32, piv32, g32 = M.lu_factor(A, R32)
    LU11, piv11, g11 = M.lu_factor(A, R11)

    # κ∞ 估计（Hager）；κ 很大时会低估，故同时保留按构造的 κ2
    try:
        kap_inf = M.cond_est(A, LU64, piv64)
    except ZeroDivisionError:
        kap_inf = float("inf")

    xtn = M.norm_inf(xt)
    bnorm = M.norm2(b)

    def ferr(x):
        return M.norm_inf([x[i] - xt[i] for i in range(n)]) / xtn

    def relres(x):
        return M.norm2(M.residual(A, b, x)) / bnorm

    x_ref = M.lu_solve(LU64, piv64, b)
    base = ferr(x_ref)

    rows = []
    for (name, pf, ps, psolve, kind) in VARIANTS:
        LUp = {53: LU64, 24: LU32, 11: LU11}[pf]
        pivp = {53: piv64, 24: piv32, 11: piv11}[pf]
        growth = {53: g64, 24: g32, 11: g11}[pf]
        if ps != pf:
            LUp = quantize_factors(LUp, ps)
        rsolve = None if psolve >= 53 else M.rounder(psolve)

        iters = 0
        inner = 0
        try:
            if kind == "none":
                x = M.lu_solve(LUp, pivp, b, rsolve)
            elif kind == "ir":
                x, iters, h = M.ir(A, b, LUp, pivp, rnd_solve=rsolve,
                                   maxit=30, tol=1e-15)
            else:
                x, iters, h, inner = M.gmres_ir(A, b, LUp, pivp,
                                                rnd_solve=rsolve, maxit=8,
                                                inner_tol=1e-12, inner_maxit=n)
        except ZeroDivisionError:
            rows.append(dict(family=fam, n=n, seed=seed, kappa2=kap2,
                             kappa_inf=kap_inf, variant=name, ferr=float("inf"),
                             ratio=float("inf"), relres=float("inf"), iters=-1,
                             inner=0, growth=growth, cost=0.0, ok=0))
            continue

        fe = ferr(x)
        rr = relres(x)
        ratio = fe / base if base > 0 else float("inf")

        # FP64 等价代价
        c = (2.0 / 3.0) * n ** 3 / SPEED[pf] + 2.0 * n ** 2 / SPEED[53]
        c += iters * (2.0 * n ** 2 / SPEED[psolve] + 2.0 * n ** 2 / SPEED[53])
        if inner:
            c += inner * (2.0 * n ** 2 / SPEED[53] + 2.0 * n ** 2 / SPEED[psolve]
                          + 2.0 * n ** 2 * 1.0)

        rows.append(dict(family=fam, n=n, seed=seed, kappa2=kap2,
                         kappa_inf=kap_inf, variant=name, ferr=fe, ratio=ratio,
                         relres=rr, iters=iters, inner=inner, growth=growth,
                         cost=c, ok=1))
    return rows, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    default_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "results", "scan.csv")
    ap.add_argument("--out", default=default_out)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()

    jobs = []
    ks = [1e0, 1e2, 1e4, 1e6, 1e7, 1e8, 1e9, 1e10, 1e12, 1e14]
    if a.quick:
        ks = [1e2, 1e6, 1e8, 1e10]
    for k in ks:
        for s in range(1, (1 if a.quick else a.seeds) + 1):
            jobs.append(("kappa", 64, s, k))
    if not a.quick:
        for k in (1e8, 1e12):
            for s in (1, 2):
                jobs.append(("kappa", 32, s, k))
        for k in (1e6, 1e10):
            for s in (1, 2):
                jobs.append(("kappa", 128, s, k))
    for s in (1, 2):
        jobs.append(("diagdom", 64, s, 0.0))
        jobs.append(("circuit", 64, s, 0.0))
    for n in (16, 32, 40):
        jobs.append(("wilkinson", n, 1, 0.0))
    for m in (8, 16, 24):
        jobs.append(("laplace2d", m * m, 1, 0.0))
    jobs.append(("laplace1d", 200, 1, 0.0))

    print("jobs:", len(jobs))
    t0 = time.time()
    allrows = []
    for i, j in enumerate(jobs):
        rows, dt = run_one(j)
        allrows.extend(rows)
        if i % 5 == 0:
            print("  %d/%d  last=%.1fs  elapsed=%.0fs"
                  % (i + 1, len(jobs), dt, time.time() - t0), flush=True)

    fields = ["family", "n", "seed", "kappa2", "kappa_inf", "variant", "ferr",
              "ratio", "relres", "iters", "inner", "growth", "cost", "ok"]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(allrows, key=lambda r: (r["family"], r["n"], r["seed"],
                                                r["kappa2"], r["variant"])):
            w.writerow({k: r[k] for k in fields})
    print("wrote", a.out, len(allrows), "rows in %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
