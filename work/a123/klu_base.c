// ============================================================================
// klu_base.c — KLU 基线（外部参照），与 mp_lu_bench 同矩阵、同输入、
//              同计时口径（warmup 1 次 + R 次重复，报中位数与最小值）
//
// 目的：回答"我们的 GPU 并行因子/三角求解相对成熟 CPU 直接解法快多少"。
//       用 KLU 默认配置（AMD + BTF + 默认缩放与 pivot 容差），单线程。
//
// 编译（cuspice_cpu 根目录下）：
//   gcc -O2 -o /tmp/klu_base klu_base.c src/maths/KLU/.libs/libKLU.a -I src/include/ngspice -lm
// 用法：./klu_base <s0.mtx> <s0.rhs> [reps]
// ============================================================================
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

#include "ngspice/klu.h"

typedef struct { int n; long nnz; int *row, *col; double *val; double *b; } s0mat;

static double now_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static int read_s0(const char *mp, const char *rp, s0mat *M)
{
    FILE *f = fopen(mp, "r");
    char line[512];
    long cap = 1024;
    if (!f) { fprintf(stderr, "open fail %s\n", mp); return 1; }
    if (!fgets(line, sizeof line, f)) return 1;
    if (sscanf(line, "n %d", &M->n) != 1) { fprintf(stderr, "bad header\n"); return 1; }
    M->row = (int *)malloc(cap * sizeof(int));
    M->col = (int *)malloc(cap * sizeof(int));
    M->val = (double *)malloc(cap * sizeof(double));
    M->nnz = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] != 'A') continue;
        if (M->nnz >= cap) {
            cap *= 2;
            M->row = (int *)realloc(M->row, cap * sizeof(int));
            M->col = (int *)realloc(M->col, cap * sizeof(int));
            M->val = (double *)realloc(M->val, cap * sizeof(double));
        }
        if (sscanf(line, "A %d %d %lf", &M->row[M->nnz], &M->col[M->nnz],
                   &M->val[M->nnz]) != 3) continue;
        M->nnz++;
    }
    fclose(f);
    M->b = (double *)calloc((size_t)M->n + 1, sizeof(double));
    if (rp) {
        f = fopen(rp, "r");
        if (f) {
            while (fgets(line, sizeof line, f)) {
                int idx; double v;
                if (sscanf(line, "RHS %d %lf", &idx, &v) == 2 && idx >= 1 && idx <= M->n)
                    M->b[idx] = v;
            }
            fclose(f);
        }
    }
    for (int i = 1; i <= M->n; i++) if (M->b[i] == 0) M->b[i] = 1.0;
    return 0;
}

/* 三元组 → CSC（0 基行号、0 基列指针，Ap[n]=nnz） */
static void to_csc(const s0mat *M, int **Ap_out, int **Ai_out, double **Ax_out)
{
    int n = M->n;
    int *Ap = (int *)calloc((size_t)n + 1, sizeof(int));
    int *Ai = (int *)malloc((size_t)M->nnz * sizeof(int));
    double *Ax = (double *)malloc((size_t)M->nnz * sizeof(double));
    int *cur = (int *)malloc((size_t)n * sizeof(int));
    for (long k = 0; k < M->nnz; k++) Ap[M->col[k]]++;      /* 列是 1 基 */
    for (int j = 0; j < n; j++) Ap[j + 1] += Ap[j];
    memcpy(cur, Ap, (size_t)n * sizeof(int));
    for (long k = 0; k < M->nnz; k++) {
        int j = M->col[k] - 1;
        int p = cur[j]++;
        Ai[p] = M->row[k] - 1;
        Ax[p] = M->val[k];
    }
    free(cur);
    *Ap_out = Ap; *Ai_out = Ai; *Ax_out = Ax;
}

static double residual(const s0mat *M, const double *x)
{
    double num = 0, den = 0;
    double *r = (double *)calloc((size_t)M->n, sizeof(double));
    for (long k = 0; k < M->nnz; k++)
        r[M->row[k] - 1] += M->val[k] * x[M->col[k] - 1];
    for (int i = 0; i < M->n; i++) {
        double d = r[i] - M->b[i + 1];
        num += d * d;
        den += M->b[i + 1] * M->b[i + 1];
    }
    free(r);
    return sqrt(num / den);
}

static int cmpd(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s <s0.mtx> <s0.rhs> [reps]\n", argv[0]); return 2; }
    int reps = (argc >= 4) ? atoi(argv[3]) : 5;
    int ord = (argc >= 5) ? atoi(argv[4]) : 0;   /* 0=AMD 1=COLAMD 2=natural */
    if (reps < 1) reps = 5;

    s0mat M;
    if (read_s0(argv[1], argv[2], &M)) return 1;
    int n = M.n;

    int *Ap, *Ai;
    double *Ax;
    to_csc(&M, &Ap, &Ai, &Ax);

    klu_common Common;
    if (!klu_defaults(&Common)) { fprintf(stderr, "klu_defaults fail\n"); return 1; }
    Common.btf = 1;          /* 默认：AMD + BTF */
    Common.scale = 2;        /* 默认：maxnorm 缩放 */
    Common.tol = 0.001;
    Common.ordering = ord;

    double *x = (double *)malloc((size_t)n * sizeof(double));
    double *b = (double *)malloc((size_t)n * sizeof(double));
    memcpy(b, M.b + 1, (size_t)n * sizeof(double));

    double ta[8], tf[8], ts[8], resid = -1;
    double analyze_ms = -1, factor_med = -1, factor_min = -1, solve_med = -1, solve_min = -1;
    int lnz = -1, unz = -1, ok = 0;

    for (int rep = 0; rep < reps + 1; rep++) {      /* rep 0 = warmup */
        double t0 = now_ms();
        klu_symbolic *Sym = klu_analyze(n, Ap, Ai, &Common);
        double t1 = now_ms();
        if (!Sym) { fprintf(stderr, "klu_analyze failed\n"); return 1; }
        klu_numeric *Num = klu_factor(Ap, Ai, Ax, Sym, &Common);
        double t2 = now_ms();
        if (!Num) { fprintf(stderr, "klu_factor failed\n"); return 1; }
        memcpy(x, b, (size_t)n * sizeof(double));
        klu_solve(Sym, Num, n, 1, x, &Common);
        double t3 = now_ms();

        lnz = Num->lnz; unz = Num->unz;
        resid = residual(&M, x);
        if (rep > 0) {
            ta[rep - 1] = t1 - t0;
            tf[rep - 1] = t2 - t1;
            ts[rep - 1] = t3 - t2;
        }
        klu_free_numeric(&Num, &Common);
        klu_free_symbolic(&Sym, &Common);
        ok = 1;
    }
    if (!ok) return 1;

    double a[8], f2[8], s2[8];
    int r = (reps <= 8) ? reps : 8;
    memcpy(a, ta, r * sizeof(double));
    memcpy(f2, tf, r * sizeof(double));
    memcpy(s2, ts, r * sizeof(double));
    qsort(a, r, sizeof(double), cmpd);
    qsort(f2, r, sizeof(double), cmpd);
    qsort(s2, r, sizeof(double), cmpd);
    analyze_ms = a[r / 2];
    factor_med = f2[r / 2]; factor_min = f2[0];
    solve_med = s2[r / 2];  solve_min = s2[0];

    printf("KLU(ord=%d): n=%d nnz=%ld lnz=%d unz=%d (L+U=%d) analyze=%.3f ms "
           "factor=%.3f ms (min %.3f) solve=%.3f ms (min %.3f) res=%.3e\n",
           ord, n, M.nnz, lnz, unz, lnz + unz, analyze_ms, factor_med, factor_min,
           solve_med, solve_min, resid);
    printf("JSON:{\"solver\":\"klu\",\"n\":%d,\"nnz\":%ld,\"lnz\":%d,\"unz\":%d,"
           "\"analyze_ms\":%.3f,\"factor_ms\":%.3f,\"factor_min_ms\":%.3f,"
           "\"solve_ms\":%.3f,\"solve_min_ms\":%.3f,\"res\":%.3e,\"reps\":%d}\n",
           n, M.nnz, lnz, unz, analyze_ms, factor_med, factor_min,
           solve_med, solve_min, resid, reps);
    return 0;
}
