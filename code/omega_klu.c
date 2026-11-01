/* omega_klu.c -- 在电路矩阵上测分量式增长因子（支持 BTF 与行/列均衡）
 *
 *   rho = || diag(1/r) * (|L||U| + |F|) * diag(1/c) * e ||_inf / ||A||_inf
 *
 * 其中 (r,c) 是均衡缩放（eq=1 时），L/U 是 BTF 对角块的因子，F 是块外元素。
 * eq=0 时 r=c=1，退化为 || |L||U| + |F| ||_inf / ||A||_inf。
 *
 * 理论联系：  |dA| <= u_f * diag(1/r) (|L||U|+|F|) diag(1/c)
 *            rho 就是低精度分解的可达相对残差 / u_f。
 *
 * 用法: ./omega_klu <mtx> [btf] [klu_scale] [eq]
 *   btf=0/1    是否使用 BTF（生产配置为 1）
 *   klu_scale  KLU 内建缩放（生产由外部 MC64 完成，这里用 eq 近似）
 *   eq=0/1     是否先做行/列最大范数均衡
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "klu.h"

typedef struct { int r, c; double v; } Trip;

static void *xmalloc(size_t nb)
{
    void *p = malloc(nb ? nb : 1);
    if (!p) { fprintf(stderr, "OOM %zu bytes\n", nb); exit(1); }
    return p;
}

static int cmp_trip(const void *a, const void *b)
{
    const Trip *x = (const Trip *)a, *y = (const Trip *)b;
    if (x->c != y->c) return x->c - y->c;
    return x->r - y->r;
}

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: %s file.mtx [btf] [klu_scale] [eq]\n", argv[0]); return 2; }
    int use_btf   = (argc > 2) ? atoi(argv[2]) : 0;
    int use_scale = (argc > 3) ? atoi(argv[3]) : 0;
    int use_eq    = (argc > 4) ? atoi(argv[4]) : 0;
    double use_tol = (argc > 5) ? atof(argv[5]) : 0.001;  /* 1.0 = 静态/对角主元 */

    FILE *f = fopen(argv[1], "r");
    if (!f) { perror("open"); return 1; }

    char line[1024];
    long n = 0, n2 = 0, nnz_decl = 0;
    int sym = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '%' || line[0] == '#') {
            if (strstr(line, "symmetric") || strstr(line, "Symmetric")) sym = 1;
            continue;
        }
        if (line[0] == '\n' || line[0] == '\r') continue;
        break;
    }
    if (sscanf(line, "%ld %ld %ld", &n, &n2, &nnz_decl) < 2) {
        fprintf(stderr, "bad header: %s\n", line); return 1;
    }

    long cap = (nnz_decl > 0 ? nnz_decl : 1024) * (sym ? 2 : 1) + 16;
    Trip *T = xmalloc(sizeof(Trip) * cap);
    long cnt = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '%' || line[0] == '#' || line[0] == '\n') continue;
        long ii, jj; double vv;
        if (sscanf(line, "%ld %ld %lf", &ii, &jj, &vv) != 3) {
            if (sscanf(line, "%ld %ld", &ii, &jj) != 2) continue;
            vv = 1.0;
        }
        if (vv == 0.0) continue;
        if (cnt + 2 >= cap) {
            cap *= 2;
            T = realloc(T, sizeof(Trip) * cap);
            if (!T) { fprintf(stderr, "OOM\n"); return 1; }
        }
        T[cnt].r = (int)(ii - 1); T[cnt].c = (int)(jj - 1); T[cnt].v = vv; cnt++;
        if (sym && ii != jj) {
            T[cnt].r = (int)(jj - 1); T[cnt].c = (int)(ii - 1); T[cnt].v = vv; cnt++;
        }
    }
    fclose(f);

    /* ||A||_inf（原始矩阵） */
    double *rowmax = xmalloc(sizeof(double) * n);
    double *colmax = xmalloc(sizeof(double) * n);
    double *rowsum = xmalloc(sizeof(double) * n);
    for (long i = 0; i < n; i++) { rowmax[i] = 0.0; colmax[i] = 0.0; rowsum[i] = 0.0; }
    for (long k = 0; k < cnt; k++) {
        double a = fabs(T[k].v);
        rowsum[T[k].r] += a;
        if (a > rowmax[T[k].r]) rowmax[T[k].r] = a;
        if (a > colmax[T[k].c]) colmax[T[k].c] = a;
    }
    double normA = 0.0;
    for (long i = 0; i < n; i++) if (rowsum[i] > normA) normA = rowsum[i];

    /* 均衡：A <- diag(r) A diag(c)，rv=1/r, cv=1/c 用于还原 */
    double *rv = xmalloc(sizeof(double) * n);
    double *cv = xmalloc(sizeof(double) * n);
    for (long i = 0; i < n; i++) { rv[i] = 1.0; cv[i] = 1.0; }
    if (use_eq) {
        for (long i = 0; i < n; i++) {
            rv[i] = (rowmax[i] > 0.0) ? rowmax[i] : 1.0;
            cv[i] = (colmax[i] > 0.0) ? colmax[i] : 1.0;
        }
        /* A_s = diag(1/rm) A diag(1/cm)，还原时乘回 rm、用 cm 作列权 */
        for (long k = 0; k < cnt; k++) T[k].v /= (rv[T[k].r] * cv[T[k].c]);
    }

    qsort(T, cnt, sizeof(Trip), cmp_trip);

    int *Ap = xmalloc(sizeof(int) * (n + 1));
    memset(Ap, 0, sizeof(int) * (n + 1));
    for (long k = 0; k < cnt; k++) Ap[T[k].c + 1]++;
    for (long j = 0; j < n; j++) Ap[j + 1] += Ap[j];
    int nnz = Ap[n];
    int *Ai = xmalloc(sizeof(int) * (nnz + 1));
    double *Ax = xmalloc(sizeof(double) * (nnz + 1));
    for (long j = 0; j < n; j++) {
        int out = Ap[j];
        for (long k = Ap[j]; k < Ap[j + 1]; k++) {
            if (out > Ap[j] && Ai[out - 1] == T[k].r) Ax[out - 1] += T[k].v;
            else { Ai[out] = T[k].r; Ax[out] = T[k].v; out++; }
        }
        Ap[j + 1] = out;
    }
    nnz = Ap[n];
    free(T);

    klu_common Common;
    klu_defaults(&Common);
    Common.btf = use_btf;
    Common.scale = use_scale;
    Common.ordering = 0;
    Common.tol = use_tol;

    klu_symbolic *Sym = klu_analyze((int)n, Ap, Ai, &Common);
    if (!Sym) { printf("%s n=%ld ANALYZE_FAIL\n", argv[1], n); return 3; }
    klu_numeric *Num = klu_factor(Ap, Ai, Ax, Sym, &Common);
    if (!Num) { printf("%s n=%ld FACTOR_FAIL status=%d\n", argv[1], n, Common.status); return 3; }

    int lnz = (int)Num->lnz, unz = (int)Num->unz, nzoff = (int)Num->nzoff;
    int *Lp = xmalloc(sizeof(int) * (n + 1)), *Li = xmalloc(sizeof(int) * (lnz + 1));
    double *Lx = xmalloc(sizeof(double) * (lnz + 1));
    int *Up = xmalloc(sizeof(int) * (n + 1)), *Ui = xmalloc(sizeof(int) * (unz + 1));
    double *Ux = xmalloc(sizeof(double) * (unz + 1));
    int *Fp = xmalloc(sizeof(int) * (n + 1));
    int *Fi = xmalloc(sizeof(int) * (nzoff + 1));
    double *Fx = xmalloc(sizeof(double) * (nzoff + 1));
    for (long j = 0; j <= n; j++) Fp[j] = 0;

    if (!klu_extract(Num, Sym, Lp, Li, Lx, Up, Ui, Ux,
                     Fp, Fi, Fx, NULL, NULL, NULL, NULL, &Common)) {
        printf("%s n=%ld EXTRACT_FAIL\n", argv[1], n); return 3;
    }

    /* ||L||_inf（KLU 的 L 显式含单位对角） */
    for (long i = 0; i < n; i++) rowsum[i] = 0.0;
    for (long j = 0; j < n; j++)
        for (int k = Lp[j]; k < Lp[j + 1]; k++) rowsum[Li[k]] += fabs(Lx[k]);
    double normL = 0.0;
    for (long i = 0; i < n; i++) if (rowsum[i] > normL) normL = rowsum[i];

    memset(rowsum, 0, sizeof(double) * n);
    for (long j = 0; j < n; j++)
        for (int k = Up[j]; k < Up[j + 1]; k++) rowsum[Ui[k]] += fabs(Ux[k]);
    double normU = 0.0;
    for (long i = 0; i < n; i++) if (rowsum[i] > normU) normU = rowsum[i];

    /* G = |L||U| + |F|，算 G * cv */
    double *t = xmalloc(sizeof(double) * n), *s = xmalloc(sizeof(double) * n);
    for (long i = 0; i < n; i++) t[i] = 0.0;
    for (long j = 0; j < n; j++)
        for (int k = Up[j]; k < Up[j + 1]; k++) t[Ui[k]] += fabs(Ux[k]) * cv[j];
    for (long i = 0; i < n; i++) s[i] = 0.0;
    for (long j = 0; j < n; j++)
        for (int k = Lp[j]; k < Lp[j + 1]; k++) s[Li[k]] += fabs(Lx[k]) * t[j];
    for (long j = 0; j < n; j++)
        for (int k = Fp[j]; k < Fp[j + 1]; k++) s[Fi[k]] += fabs(Fx[k]) * cv[j];

    for (long i = 0; i < n; i++) s[i] *= rv[i];
    double normG = 0.0;
    for (long i = 0; i < n; i++) if (s[i] > normG) normG = s[i];

    /* k_inf = ||A||_inf * ||A^{-1}||_inf （对传入 KLU 的矩阵） */
    double *x = xmalloc(sizeof(double) * n), *y = xmalloc(sizeof(double) * n);
    double *zz = xmalloc(sizeof(double) * n);
    for (long i = 0; i < n; i++) x[i] = 1.0 / (double)n;
    double est = 0.0;
    for (int it = 0; it < 10; it++) {
        memcpy(y, x, sizeof(double) * n);
        klu_tsolve(Sym, Num, (int)n, 1, y, &Common);
        double s1 = 0.0;
        for (long i = 0; i < n; i++) s1 += fabs(y[i]);
        if (s1 <= est) break;
        est = s1;
        for (long i = 0; i < n; i++) zz[i] = (y[i] >= 0.0) ? 1.0 : -1.0;
        memcpy(y, zz, sizeof(double) * n);
        klu_solve(Sym, Num, (int)n, 1, y, &Common);
        int jm = 0; double am = 0.0;
        for (long i = 0; i < n; i++) if (fabs(y[i]) > am) { am = fabs(y[i]); jm = (int)i; }
        double zx = 0.0;
        for (long i = 0; i < n; i++) zx += zz[i] * x[i];
        if (am <= zx) break;
        for (long i = 0; i < n; i++) x[i] = 0.0;
        x[jm] = 1.0;
    }
    double kA_solver = 0.0;
    for (long j = 0; j < n; j++) {
        double cs = 0.0;
        for (int k = Ap[j]; k < Ap[j + 1]; k++) cs += fabs(Ax[k]);
        if (cs > kA_solver) kA_solver = cs;
    }
    double kinf = kA_solver * est;

    /* 自检：解 A x = A*1，看真实残差 */
    double *b = xmalloc(sizeof(double) * n);
    for (long i = 0; i < n; i++) b[i] = 0.0;
    for (long j = 0; j < n; j++)
        for (int k = Ap[j]; k < Ap[j + 1]; k++) b[Ai[k]] += Ax[k];
    memcpy(x, b, sizeof(double) * n);
    klu_solve(Sym, Num, (int)n, 1, x, &Common);
    double rmax = 0.0, xmax = 0.0, Amax = 0.0, bmax = 0.0;
    for (long i = 0; i < n; i++) if (fabs(b[i]) > bmax) bmax = fabs(b[i]);
    for (long i = 0; i < n; i++) if (fabs(x[i]) > xmax) xmax = fabs(x[i]);
    for (long j = 0; j < n; j++) {
        double cs = 0.0;
        for (int k = Ap[j]; k < Ap[j + 1]; k++) cs += fabs(Ax[k]);
        if (cs > Amax) Amax = cs;
    }
    double *ax = xmalloc(sizeof(double) * n);
    for (long i = 0; i < n; i++) ax[i] = 0.0;
    for (long j = 0; j < n; j++)                     /* CSC: 按列累加到行 */
        for (int k = Ap[j]; k < Ap[j + 1]; k++) ax[Ai[k]] += Ax[k] * x[j];
    for (long i = 0; i < n; i++) {
        double r = fabs(ax[i] - b[i]);
        if (r > rmax) rmax = r;
    }
    /* 标准向后误差：‖r‖∞ / (‖A‖∞‖x‖∞ + ‖b‖∞) */
    double den = Amax * xmax + bmax;
    double res = (den > 0.0) ? rmax / den : 0.0;

    printf("%-34s st=%-3d sc=%-7d n=%-7ld nblk=%-5d fill=%-9d nzoff=%-7d rho=%-11.4e kA=%-10.3e kinf=%-11.4e nL=%-8.2e nU=%-9.3e\n",
           argv[1], Common.status, Common.singular_col, n, (int)Sym->nblocks, lnz + unz, nzoff,
           normG / normA, normA, kinf, normL, normU);
    printf("    res=%.3e\n", res);
    fflush(stdout);

    klu_free_numeric(&Num, &Common);
    klu_free_symbolic(&Sym, &Common);
    return 0;
}
