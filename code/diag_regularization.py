"""diag_regularization.py -- 诊断：低精度分解如何把病态矩阵"正则化"

对每个 κ 与分解精度 u_f，记录:
  - 最后一个主元 |U_nn|（噪声地板）
  - ||M^{-1}|| 的幂迭代下界
  - 向后误差 ||A - LU||_F / ||A||_F
  - 预条件算子偏差 ||A M^{-1} - I||_F
输出 results/reg.csv
"""
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplib as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "reg.csv")
R64 = M.rounder(53)


def inv_norm_lb(LU, piv, n, iters=120):
    """||M^{-1}||_2 的幂迭代下界（不做转置，量级参考）。"""
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


def recon(A, LU, piv):
    n = len(A)
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


def main():
    n = 48
    rows = []
    for kap in (1e4, 1e6, 1e8, 1e10, 1e12, 1e14):
        A, _ = M.make_kappa_matrix(n, kap, seed=4)
        for p in (53, 24, 11):
            LU, piv, g = M.lu_factor(A, M.rounder(p))
            rec = recon(A, LU, piv)
            # ||A M^{-1} - I||_F
            B = [[0.0] * n for _ in range(n)]
            for j in range(n):
                e = [0.0] * n
                e[j] = 1.0
                c = M.lu_solve(LU, piv, e)
                for i in range(n):
                    B[i][j] = sum(A[i][k] * c[k] for k in range(n))
            dev = math.sqrt(sum((B[i][j] - (1.0 if i == j else 0.0)) ** 2
                                for i in range(n) for j in range(n)))
            rows.append(dict(kappa=kap, u_f=p, u=2.0 ** -(p - 1),
                             unn=abs(LU[n - 1][n - 1]),
                             invnorm=inv_norm_lb(LU, piv, n),
                             backerr=rel_fro(A, rec),
                             precond_dev=dev,
                             growth=g))
            print("kappa=%8.0e u_f=%2d |U_nn|=%.2e ||M^-1||=%.1e backerr=%.1e dev=%.1e"
                  % (kap, p, abs(LU[n - 1][n - 1]), rows[-1]["invnorm"],
                     rows[-1]["backerr"], dev), flush=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kappa", "u_f", "u", "unn", "invnorm",
                                          "backerr", "precond_dev", "growth"])
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
