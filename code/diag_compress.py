"""diag_compress.py -- 对照实验：因子"压缩" vs "低精度重算"

同一精度 u_q 下两种得到因子 M 的方式：
  recompute : 直接在 u_q 下做 LU（舍入误差逐次累积）
  compress  : FP64 下做 LU，再把 L/U 逐元素舍入到 u_q（相对误差）

对每种组合记录：
  unn        最后一个主元的绝对值（σ_min 的代理）
  invnorm    ||M^{-1}||_2 的幂迭代下界
  backerr    ||A - LU||_F / ||A||_F
  precond    ||A M^{-1} - I||_F（GMRES 精化的关键量）

输出 results/reg2.csv（列: kappa,u_f,mode,unn,invnorm,backerr,precond）
"""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplib as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "reg2.csv")
R64 = M.rounder(53)


def inv_norm_lb(LU, piv, n, iters=120):
    v = [1.0 / math.sqrt(n)] * n
    s = 0.0
    for _ in range(iters):
        w = M.lu_solve(LU, piv, v)
        nr = math.sqrt(sum(t * t for t in w))
        if nr == 0.0 or not math.isfinite(nr):
            break
        s = nr
        v = [t / nr for t in w]
    return s


def recon(LU, piv):
    n = len(LU)
    L = [[0.0] * n for _ in range(n)]
    U = [[0.0] * n for _ in range(n)]
    for i in range(n):
        L[i][i] = 1.0
        for j in range(n):
            if j < i:
                L[i][j] = LU[i][j]
            else:
                U[i][j] = LU[i][j]
    P = [[0.0] * n for _ in range(n)]
    for i in range(n):
        r = piv[i]
        for j in range(n):
            P[r][j] = sum(L[i][k] * U[k][j] for k in range(n))
    return P


def rel_fro(A, B):
    num = math.sqrt(sum((A[i][j] - B[i][j]) ** 2
                        for i in range(len(A)) for j in range(len(A))))
    den = math.sqrt(sum(A[i][j] ** 2 for i in range(len(A)) for j in range(len(A))))
    return num / den if den else 0.0


def precond_dev(A, LU, piv, n):
    B = [[0.0] * n for _ in range(n)]
    for j in range(n):
        e = [0.0] * n
        e[j] = 1.0
        c = M.lu_solve(LU, piv, e)
        for i in range(n):
            B[i][j] = sum(A[i][k] * c[k] for k in range(n))
    return math.sqrt(sum((B[i][j] - (1.0 if i == j else 0.0)) ** 2
                         for i in range(n) for j in range(n)))


def measure(A, LU, piv, n, kappa, p, mode):
    rec = recon(LU, piv)
    row = dict(kappa=kappa, u_f=p, mode=mode,
               unn=abs(LU[n - 1][n - 1]),
               invnorm=inv_norm_lb(LU, piv, n),
               backerr=rel_fro(A, rec),
               precond=precond_dev(A, LU, piv, n))
    print("  k=%8.0e u_q=%2d %-9s |U_nn|=%.2e inv=%.1e backerr=%.1e dev=%.1e"
          % (kappa, p, mode, row["unn"], row["invnorm"], row["backerr"], row["precond"]),
          flush=True)
    return row


def main():
    n = 48
    rows = []
    for kap in (1e4, 1e6, 1e8, 1e10, 1e12, 1e14):
        A, _ = M.make_kappa_matrix(n, kap, seed=4)
        LU64, piv64, _ = M.lu_factor(A, R64)
        lu64_copy = [r[:] for r in LU64]
        rows.append(measure(A, LU64, piv64, n, kap, 53, "fp64"))
        for p in (24, 11):
            LU, piv, _ = M.lu_factor(A, M.rounder(p))
            rows.append(measure(A, LU, piv, n, kap, p, "recompute"))
            r = M.rounder(p)
            LUc = [[r(v) for v in row] for row in lu64_copy]
            rows.append(measure(A, LUc, piv64, n, kap, p, "compress"))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kappa", "u_f", "mode", "unn",
                                          "invnorm", "backerr", "precond"])
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT, len(rows), "rows")


if __name__ == "__main__":
    main()
