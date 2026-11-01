"""
mplib.py -- 纯 Python 的混合精度稠密线性代数实验内核（不依赖 numpy / LAPACK）

设计要点
--------
1. 精度用"有效位数 p（含隐含位）"参数化：
       p = 53 -> FP64 (binary64)
       p = 24 -> FP32 (binary32)
       p = 11 -> TF32 / FP16 尾数
       p =  8 -> BF16 尾数
   每次算术结果都过一遍 round_p，以模拟"在该精度下计算"。因为两个 p<=27 位的
   数之积在 double 中精确，round(a*b+c) 等价于单次舍入的 FMA，故可忠实模拟
   "低精度 FMA"。

2. 舍入函数可组合：factor / solve / residual 各自可以指定不同的 p，
   对应文献中 u_f（分解精度）/ u（工作精度）/ u_r（残差精度）三个槽位。

3. 所有矩阵用 list-of-list 表示，double 存储。
"""

import math
import struct

__all__ = [
    "rounder", "lu_factor", "lu_solve", "matvec", "norm_inf", "norm2",
    "cond_est", "gmres", "gmres_ir", "ir", "make_kappa_matrix",
    "make_laplacian_2d", "make_laplacian_1d", "make_wilkinson",
    "make_diag_dominant", "make_sparse_circuit", "matmul", "transpose",
]

# ---------------------------------------------------------------- rounding ---

_F32 = struct.Struct("f")


def _r32(x):
    try:
        return _F32.unpack(_F32.pack(x))[0]
    except (OverflowError, struct.error):
        return math.copysign(float("inf"), x)


def rounder(p):
    """返回把 double 舍入到 p 位有效位的函数。"""
    if p >= 53:
        return lambda x: x
    if p == 24:
        return _r32

    def r(x):
        if x == 0.0 or x != x or x == float("inf") or x == float("-inf"):
            return x
        m, e = math.frexp(x)
        s = 1.0
        if m < 0.0:
            s = -1.0
            m = -m
        q = round(math.ldexp(m, p))       # Python round = 四舍六入五成双 (RNE)
        return math.ldexp(s * q, e - p)

    return r


# ------------------------------------------------------------------- LU -----

def lu_factor(A, rnd, pivot=True):
    """右看 (right-looking) LU + 部分主元。返回 (LU 就地, piv, growth)。

    每个乘加都过一次 rnd，模拟目标精度下的 FMA。piv 记录行交换。
    """
    n = len(A)
    LU = [row[:] for row in A]
    piv = list(range(n))
    for k in range(n):
        if pivot:
            amax = abs(LU[k][k])
            p = k
            for i in range(k + 1, n):
                v = abs(LU[i][k])
                if v > amax:
                    amax = v
                    p = i
            if p != k:
                LU[k], LU[p] = LU[p], LU[k]
                piv[k], piv[p] = piv[p], piv[k]
        akk = LU[k][k]
        if akk == 0.0:
            raise ZeroDivisionError("zero pivot at k=%d" % k)
        rk = LU[k]
        for i in range(k + 1, n):
            ri = LU[i]
            lik = rnd(ri[k] / akk)
            ri[k] = lik
            if lik != 0.0:
                for j in range(k + 1, n):
                    ri[j] = rnd(ri[j] - lik * rk[j])
    # 增长因子 rho = max|U| / max|A|
    amax_a = 0.0
    amax_u = 0.0
    for i in range(n):
        ai = A[i]
        ui = LU[i]
        for j in range(n):
            v = abs(ai[j])
            if v > amax_a:
                amax_a = v
            if j >= i:
                v = abs(ui[j])
                if v > amax_u:
                    amax_u = v
    growth = amax_u / amax_a if amax_a > 0.0 else 0.0
    return LU, piv, growth


def lu_solve(LU, piv, b, rnd=None):
    """用 LU 因子解 Ax=b。rnd=None 表示三角求解在 double 中做（u=FP64）。"""
    n = len(b)
    x = [b[piv[i]] for i in range(n)]
    if rnd is None:
        for i in range(n):
            Li = LU[i]
            s = x[i]
            for j in range(i):
                s -= Li[j] * x[j]
            x[i] = s
        for i in range(n - 1, -1, -1):
            Ui = LU[i]
            s = x[i]
            for j in range(i + 1, n):
                s -= Ui[j] * x[j]
            x[i] = s / Ui[i]
    else:
        for i in range(n):
            Li = LU[i]
            s = x[i]
            for j in range(i):
                s = rnd(s - Li[j] * x[j])
            x[i] = s
        for i in range(n - 1, -1, -1):
            Ui = LU[i]
            s = x[i]
            for j in range(i + 1, n):
                s = rnd(s - Ui[j] * x[j])
            x[i] = rnd(s / Ui[i])
    return x


# --------------------------------------------------------------- kernels ----

def matvec(A, x, rnd=None):
    n = len(A)
    y = [0.0] * n
    if rnd is None:
        for i in range(n):
            Ai = A[i]
            s = 0.0
            for j in range(n):
                s += Ai[j] * x[j]
            y[i] = s
    else:
        for i in range(n):
            Ai = A[i]
            s = 0.0
            for j in range(n):
                s = rnd(s + Ai[j] * x[j])
            y[i] = s
    return y


def matmul(A, B, rnd=None):
    n = len(A)
    m = len(B[0])
    C = [[0.0] * m for _ in range(n)]
    for i in range(n):
        Ai = A[i]
        Ci = C[i]
        for k in range(n):
            a = Ai[k]
            if a == 0.0:
                continue
            Bk = B[k]
            for j in range(m):
                Ci[j] += a * Bk[j]
        if rnd is not None:
            C[i] = [rnd(v) for v in Ci]
    return C


def norm_inf(v):
    return max(abs(t) for t in v) if v else 0.0


def norm2(v):
    return math.sqrt(sum(t * t for t in v))


def norm1_mat(A):
    n = len(A)
    return max(sum(abs(A[i][j]) for i in range(n)) for j in range(n))


# --------------------------------------------------------- conditioning -----

def cond_est(A, LU=None, piv=None, rnd=None):
    """Hager–Higham 1-范数条件数估计：κ1(A) = ||A||_1 · ||A^{-1}||_1。

    需要 A 与其转置的 LU 分解（各一次），内部做 ~5 次三角求解。
    """
    n = len(A)
    if LU is None:
        LU, piv, _ = lu_factor([r[:] for r in A], rnd or (lambda x: x))
    AT = transpose(A)
    LUT, pivT, _ = lu_factor(AT, rnd or (lambda x: x))
    a1 = norm1_mat(A)
    x = [1.0 / n] * n
    est = 0.0
    for _ in range(5):
        y = lu_solve(LU, piv, x)
        est = sum(abs(t) for t in y)
        if est == 0.0:
            break
        xi = [1.0 if t >= 0 else -1.0 for t in y]
        z = lu_solve(LUT, pivT, xi)          # A^{-T} xi
        j = max(range(n), key=lambda i: abs(z[i]))
        if abs(z[j]) <= sum(z[i] * x[i] for i in range(n)) * (1 + 1e-12):
            break
        x = [0.0] * n
        x[j] = 1.0
    return a1 * est


# ----------------------------------------------------------------- GMRES ----

def gmres(Aop, b, maxiter=100, tol=1e-15, rnd=None):
    """右预条件由 Aop 自带（Aop 直接是 A∘M^{-1}）。x0 = 0。返回 (x, iters, resid)。"""
    n = len(b)
    nb = norm2(b)
    if nb == 0.0:
        return [0.0] * n, 0, 0.0
    V = []
    v = [t / nb for t in b]
    V.append(v)
    H = [[0.0] * maxiter for _ in range(maxiter + 1)]
    cs = [0.0] * maxiter
    sn = [0.0] * maxiter
    g = [0.0] * (maxiter + 1)
    g[0] = nb
    it = 0
    for j in range(maxiter):
        w = Aop(V[j])
        # 修正 Gram-Schmidt 两遍
        for i in range(j + 1):
            h = sum(V[i][k] * w[k] for k in range(n))
            H[i][j] = h
            Vi = V[i]
            for k in range(n):
                w[k] -= h * Vi[k]
        for i in range(j + 1):
            h = sum(V[i][k] * w[k] for k in range(n))
            H[i][j] += h
            Vi = V[i]
            for k in range(n):
                w[k] -= h * Vi[k]
        H[j + 1][j] = norm2(w)
        nj1 = H[j + 1][j]              # 先存下来：Givens 会把它清零
        # Givens
        for i in range(j):
            t = cs[i] * H[i][j] + sn[i] * H[i + 1][j]
            H[i + 1][j] = -sn[i] * H[i][j] + cs[i] * H[i + 1][j]
            H[i][j] = t
        r = math.hypot(H[j][j], H[j + 1][j])
        if r == 0.0:
            cs[j], sn[j] = 1.0, 0.0
        else:
            cs[j] = H[j][j] / r
            sn[j] = H[j + 1][j] / r
        H[j][j] = r
        H[j + 1][j] = 0.0
        g[j + 1] = -sn[j] * g[j]
        g[j] = cs[j] * g[j]
        it = j + 1
        if abs(g[j + 1]) <= tol * nb:
            break
        if nj1 == 0.0:
            break
        V.append([t / nj1 for t in w])
    # 回代
    y = [0.0] * it
    for i in range(it - 1, -1, -1):
        s = g[i]
        for k in range(i + 1, it):
            s -= H[i][k] * y[k]
        y[i] = s / H[i][i]
    x = [0.0] * n
    for j in range(it):
        Vj = V[j]
        yj = y[j]
        for k in range(n):
            x[k] += Vj[k] * yj
    return x, it, abs(g[it]) if it > 0 else nb


# --------------------------------------------------- refinement drivers -----

def residual(A, b, x, rnd=None):
    r = matvec(A, x, rnd)
    for i in range(len(b)):
        r[i] = b[i] - r[i]
    return r


def ir(A, b, LU, piv, rnd_solve=None, rnd_res=None, maxit=20,
       tol=None, x0=None):
    """标准迭代精化（fixed-precision LU）。返回 (x, iters, hist)。"""
    n = len(b)
    x = lu_solve(LU, piv, b, rnd_solve) if x0 is None else x0[:]
    hist = []
    nb = norm2(b)
    for k in range(maxit):
        r = residual(A, b, x, rnd_res)
        nr = norm2(r)
        hist.append(nr / nb if nb else nr)
        if tol is not None and nr <= tol * nb:
            break
        if len(hist) >= 3 and hist[-1] > 0.5 * hist[-2]:
            break                      # 残差停滞：不再精化
        d = lu_solve(LU, piv, r, rnd_solve)
        for i in range(n):
            x[i] += d[i]
        if nr == 0.0:
            break
    return x, len(hist), hist


def gmres_ir(A, b, LU, piv, rnd_solve=None, rnd_res=None, maxit=10,
             inner_tol=1e-12, inner_maxit=80):
    """GMRES-IR：低精度 LU 作预条件，工作精度 GMRES 解修正方程。

    内层 GMRES 用较松的容差 inner_tol（相对当前残差），这是文献中的标准做法：
    修正方程不需要解准，只需要提供下降方向，否则内层代价会吞掉收益。
    返回 (x, outer_iters, hist, total_inner_iters)。
    """
    n = len(b)

    def m_apply(v):
        return lu_solve(LU, piv, v, rnd_solve)

    x = m_apply(b)
    hist = []
    nb = norm2(b)
    total_inner = 0

    def aop(v):
        return matvec(A, m_apply(v))

    for k in range(maxit):
        r = residual(A, b, x, rnd_res)
        nr = norm2(r)
        hist.append(nr / nb if nb else nr)
        if nr <= 1e-15 * nb or nr == 0.0:
            break
        dz, it, _ = gmres(aop, r, maxiter=inner_maxit, tol=inner_tol)
        total_inner += it
        dx = m_apply(dz)
        for i in range(n):
            x[i] += dx[i]
        if len(hist) >= 2 and hist[-1] > 0.9 * hist[-2]:
            break                     # 停滞
    return x, len(hist), hist, total_inner


# ------------------------------------------------------- matrix builders ----

class RNG:
    """可复现的轻量 PRNG（xorshift128+ 思想，够用）。"""

    def __init__(self, seed=12345):
        self.s = seed & 0xFFFFFFFFFFFFFFFF
        if self.s == 0:
            self.s = 88172645463325252

    def next_u64(self):
        x = self.s
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        self.s = x
        return x

    def rand(self):
        return (self.next_u64() >> 11) * (1.0 / 9007199254740992.0)

    def gauss(self):
        u1 = max(self.rand(), 1e-300)
        u2 = self.rand()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _orthonormal(n, rng):
    """两遍修正 Gram-Schmidt 的随机正交基（列）。"""
    cols = []
    for _ in range(n):
        v = [rng.gauss() for _ in range(n)]
        for _pass in range(2):
            for u in cols:
                d = sum(u[i] * v[i] for i in range(n))
                for i in range(n):
                    v[i] -= d * u[i]
        nv = math.sqrt(sum(t * t for t in v))
        cols.append([t / nv for t in v])
    return cols


def make_kappa_matrix(n, kappa, seed=1):
    """A = U diag(σ) V^T，σ 对数等距从 1 到 1/κ。返回 (A, 已知κ)。"""
    rng = RNG(seed)
    U = _orthonormal(n, rng)
    V = _orthonormal(n, rng)
    if n == 1:
        sig = [1.0]
    else:
        sig = [10.0 ** (-(i / (n - 1)) * math.log10(kappa)) for i in range(n)]
    A = [[0.0] * n for _ in range(n)]
    for k in range(n):
        s = sig[k]
        uk = U[k]
        vk = V[k]
        for i in range(n):
            a = s * uk[i]
            Ai = A[i]
            for j in range(n):
                Ai[j] += a * vk[j]
    return A, kappa


def make_laplacian_1d(n):
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        A[i][i] = 2.0
        if i > 0:
            A[i][i - 1] = -1.0
        if i + 1 < n:
            A[i][i + 1] = -1.0
    return A


def make_laplacian_2d(m):
    n = m * m
    A = [[0.0] * n for _ in range(n)]
    for i in range(m):
        for j in range(m):
            k = i * m + j
            A[k][k] = 4.0
            if i > 0:
                A[k][k - m] = -1.0
            if i + 1 < m:
                A[k][k + m] = -1.0
            if j > 0:
                A[k][k - 1] = -1.0
            if j + 1 < m:
                A[k][k + 1] = -1.0
    return A


def make_wilkinson(n):
    """Wilkinson 增长矩阵：diag=1, subdiag=-1, 最后一列全 1。增长因子 2^{n-1}。"""
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        A[i][i] = 1.0
        if i > 0:
            A[i][i - 1] = -1.0
        A[i][n - 1] = 1.0
    return A


def make_diag_dominant(n, seed=7):
    rng = RNG(seed)
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        s = 0.0
        for j in range(n):
            if i != j:
                v = rng.gauss() * 0.3
                A[i][j] = v
                s += abs(v)
        A[i][i] = s + 1.0
    return A


def make_sparse_circuit(n, seed=11):
    """类 MNA 稀疏矩阵：对角占优 + 少量强非对称耦合，κ 中等。"""
    rng = RNG(seed)
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        A[i][i] = 1.0 + 10.0 * rng.rand()
        if i + 1 < n:
            A[i][i + 1] = -rng.rand()
            A[i + 1][i] = -rng.rand()
        if i + 3 < n:
            A[i][i + 3] = 0.5 * rng.gauss()
    return A


def transpose(A):
    n = len(A)
    m = len(A[0])
    return [[A[i][j] for i in range(n)] for j in range(m)]
