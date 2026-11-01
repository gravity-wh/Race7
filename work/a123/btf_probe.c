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


int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: %s <s0.mtx>\n", argv[0]); return 2; }
    s0mat M;
    if (read_s0(argv[1], NULL, &M)) return 1;
    int n = M.n;
    int *Ap, *Ai; double *Ax;
    to_csc(&M, &Ap, &Ai, &Ax);

    int ord = (argc >= 3) ? atoi(argv[2]) : 0;   /* 0=AMD 1=COLAMD */
    int btf = (argc >= 4) ? atoi(argv[3]) : 1;
    klu_common Common;
    if (!klu_defaults(&Common)) return 1;
    Common.btf = btf; Common.scale = 2; Common.tol = 0.001; Common.ordering = ord;

    klu_symbolic *S = klu_analyze(n, Ap, Ai, &Common);
    if (!S) { fprintf(stderr, "analyze failed\n"); return 1; }

    printf("ord=%d btf=%d\n", ord, btf);
    int nb = (int)S->nblocks;
    int *R = S->R;
    int hist[8] = {0};
    int maxsz = 0, minsz = 1 << 30;
    long sum2 = 0;
    for (int b = 0; b < nb; b++) {
        int sz = R[b + 1] - R[b];
        if (sz > maxsz) maxsz = sz;
        if (sz < minsz) minsz = sz;
        sum2 += (long)sz * sz;
        int k = sz <= 1 ? 0 : sz <= 4 ? 1 : sz <= 16 ? 2 : sz <= 64 ? 3 : sz <= 256 ? 4 : sz <= 1024 ? 5 : 6;
        hist[k]++;
    }
    printf("BTF: n=%d nnz=%ld nblocks=%d maxblock=%d lnz=%d unz=%d nzoff=%d "
           "sum_block_sq=%ld\n",
           n, M.nnz, nb, maxsz, (int)S->lnz, (int)S->unz, (int)S->nzoff, sum2);
    printf("HIST: 1=%d 2-4=%d 5-16=%d 17-64=%d 65-256=%d 257-1024=%d 1025+=%d\n",
           hist[0], hist[1], hist[2], hist[3], hist[4], hist[5], hist[6]);
    printf("JSON:{\"n\":%d,\"nnz\":%ld,\"nblocks\":%d,\"maxblock\":%d,\"lnz\":%d,\"unz\":%d,"
           "\"nzoff\":%d,\"sum_block_sq\":%ld}\n",
           n, M.nnz, nb, maxsz, (int)S->lnz, (int)S->unz, (int)S->nzoff, sum2);
    klu_free_symbolic(&S, &Common);
    return 0;
}
