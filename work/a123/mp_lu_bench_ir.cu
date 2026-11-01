// ============================================================================
// mp_lu_bench.cu — 混合精度 LU 分阶段基准（赛题七 R13：mixed-precision throughput）
//
// 目的：在同一矩阵、同一 COLAMD 序、同一实现风格下，对比稀疏 LU 流水线
//   两个阶段（数值分解 / 三角求解）在 fp64 与 fp32 因子存储下的吞吐差异。
//
//   精度口径（与既有求解器一致）：
//     fp64 路径 = lu_gpu.cu / lu_gpu_par.cu（fp64 存储 + fp64 计算）
//     fp32 路径 = lu_gpu_f32.cu（fp32 因子存储 + fp64 主元/工作向量——
//                 即标准"fp32 因子 + IR 兜底"设计，内存/带宽减半，稳定不降）
//
//   计时口径：cudaEvent 内核级 wall-clock；warmup 1 次后取 R 次最优（min）。
//   ST  = 单 thread 内核；PAR = 单 block 并行内核。
//   单 thread 因子仅当 n <= max_n_st（默认 15000）测量（否则数分钟级，跳过记 n/a）。
//
// 编译（race7 根目录）：
//   /usr/local/cuda-12.6/bin/nvcc -O3 -arch=sm_86 -I src/solver \
//     -I /home/gravity/g3-ws/src -I /home/gravity/n46-mix/src/include \
//     -o mp_lu_bench src/solver/mp_bench/mp_lu_bench.cu src/solver/cpu_ref_lu.c \
//     /home/gravity/n46-mix/src/maths/KLU/colamd.c \
//     /home/gravity/n46-mix/src/maths/KLU/colamd_global.c
// 用法：./mp_lu_bench <s0.mtx> <s0.rhs> [pin] [flt] [max_n_st] [reps]
//
// A1 扩展（2026-10-30）：DSH_IR=1 时追加两段迭代精化（Richardson / 一步 GMRES-IR）：
//   [fp32 IR] fp32 因子 + fp64 残差，预条件子 = fp32 因子并行三角求解
//   [fp64 IR] fp64 因子 + fp64 残差，预条件子 = fp64 因子并行三角求解
//   收敛判据 ||r||/||b|| < DSH_IR_TOL（默认 1e-10），上限 DSH_IR_MAXIT（默认 20）。
//   发散保护：残差 > 1e8 或 NaN 时停止。
//   环境：DSH_ST_REPS=n 覆盖单 thread 因子重复次数（默认 2）
// ============================================================================
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <time.h>
#include "ngspice/klu.h"   /* A12: 借用 KLU 的 AMD 排序做对照 */
extern int amd_order(int n, const int *Ap, const int *Ai, int *P,
                     double *Control, double *Info);   /* A12: A'A 上跑 AMD */

#include <cuda_runtime.h>
#include "ngspice/colamd.h"
#include "cpu_ref_lu.h"
#include "lu_gpu.h"
#include "lu_gpu_par.h"
#include "lu_gpu.cu"        // fp64 ST kernels
#include "lu_gpu_par.cu"    // fp64 PAR kernels
#include "lu_gpu_f32.cu"    // fp32 factor + trisolve kernels

#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { \
    fprintf(stderr, "CUDA FAIL %s:%d  %s: %s\n", __FILE__, __LINE__, #x, \
            cudaGetErrorString(e_)); exit(1); } } while (0)

typedef struct { int n, nnz; int *row, *col; double *val; double *b; } s0mat;

/* ---------------- s0 读取（同 test_lu_gpu.cu） ---------------- */
static int read_s0(const char *mtx_path, const char *rhs_path, s0mat *M)
{
    FILE *f = fopen(mtx_path, "r");
    char line[512]; long cap = 1024;
    if (!f) { fprintf(stderr, "open fail %s\n", mtx_path); return 1; }
    if (!fgets(line, sizeof line, f)) return 1;
    sscanf(line, "n %d", &M->n);
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
        sscanf(line, "A %d %d %lf", &M->row[M->nnz], &M->col[M->nnz],
               &M->val[M->nnz]);
        M->nnz++;
    }
    fclose(f);
    M->b = (double *)calloc((size_t)M->n + 1, sizeof(double));
    if (rhs_path) {
        f = fopen(rhs_path, "r");
        if (f) {
            while (fgets(line, sizeof line, f)) {
                int idx; double v;
                if (sscanf(line, "RHS %d %lf", &idx, &v) == 2 &&
                    idx >= 1 && idx <= M->n)
                    M->b[idx] = v;
            }
            fclose(f);
        }
    }
    for (int i = 1; i <= M->n; i++) if (M->b[i] == 0) M->b[i] = 1.0;
    return 0;
}

static void apply_flt_pin(s0mat *M, const char *flt_path, double pinv)
{
    if (!flt_path || pinv <= 0) return;
    FILE *ff = fopen(flt_path, "r");
    if (!ff) return;
    char rb[256];
    while (fgets(rb, sizeof rb, ff)) {
        int row;
        if (sscanf(rb, "F %d", &row) == 1) {
            int i = row - 1, found = 0;
            for (int k = 0; k < M->nnz; k++)
                if (M->row[k] - 1 == i && M->col[k] - 1 == i) {
                    M->val[k] += pinv; found = 1; break;
                }
            if (!found) {
                M->row = (int *)realloc(M->row, (M->nnz + 1) * sizeof(int));
                M->col = (int *)realloc(M->col, (M->nnz + 1) * sizeof(int));
                M->val = (double *)realloc(M->val, (M->nnz + 1) * sizeof(double));
                M->row[M->nnz] = i + 1; M->col[M->nnz] = i + 1;
                M->val[M->nnz] = pinv; M->nnz++;
            }
        }
    }
    fclose(ff);
}

static int run_colamd(const s0mat *M, int **q_out)
{
    int *cp = (int *)calloc((size_t)M->n + 1, sizeof(int));
    long Alen = colamd_recommended(M->nnz, M->n, M->n);
    if (Alen < 2L * M->nnz + 16L * M->n + 16)
        Alen = 2L * M->nnz + 16L * M->n + 16;
    int *Ai_copy = (int *)malloc((size_t)Alen * sizeof(int));
    int *Ap_t = (int *)calloc((size_t)M->n + 1, sizeof(int));
    for (int i = 0; i < M->nnz; i++) Ap_t[M->col[i]]++;
    for (int i = 0; i < M->n; i++) { Ap_t[i + 1] += Ap_t[i]; cp[i] = Ap_t[i]; }
    cp[M->n] = M->nnz;
    int *cur = (int *)malloc((size_t)M->n * sizeof(int));
    memcpy(cur, Ap_t, (size_t)M->n * sizeof(int));
    for (int i = 0; i < M->nnz; i++) {
        int p = cur[M->col[i] - 1]++;
        Ai_copy[p] = M->row[i] - 1;
    }
    free(cur);
    for (int c = 0; c < M->n; c++) {
        int lo = Ap_t[c], hi = Ap_t[c + 1];
        for (int a = lo + 1; a < hi; a++) {
            int key = Ai_copy[a], bb = a - 1;
            while (bb >= lo && Ai_copy[bb] > key) { Ai_copy[bb + 1] = Ai_copy[bb]; bb--; }
            Ai_copy[bb + 1] = key;
        }
    }
    double knobs[COLAMD_KNOBS] = {0};
    int stats[COLAMD_STATS] = {0};
    int ok = colamd(M->n, M->n, (int)Alen, Ai_copy, cp, knobs, stats);
    if (!ok) { fprintf(stderr, "colamd failed stats[0..3]=%d %d %d %d\n",
                       stats[0], stats[1], stats[2], stats[3]); return 1; }
    *q_out = (int *)malloc((size_t)M->n * sizeof(int));
    for (int j = 0; j < M->n; j++) (*q_out)[j] = cp[j];
    free(cp); free(Ai_copy); free(Ap_t);
    return 0;
}

static void build_csc_q(const s0mat *M, const int *q,
                        int **Ap_out, int **Ai_out, double **Ax_out,
                        int **diagrow_out);


/* ---- A12：在 A'A 的结构模式上调用 AMD，得到"列序"（与 COLAMD 同一语义，可公平对比）---- */
static int run_amd_ata(const s0mat *M, int **q_out)
{
    int n = M->n;
    /* 1) 建 CSR（按行） */
    int *Rp = (int *)calloc((size_t)n + 1, sizeof(int));
    for (long k = 0; k < M->nnz; k++) Rp[M->row[k]]++;         /* 行是 1 基 */
    for (int i = 0; i < n; i++) Rp[i + 1] += Rp[i];
    int *Ri = (int *)malloc((size_t)M->nnz * sizeof(int));
    int *cur = (int *)malloc((size_t)n * sizeof(int));
    memcpy(cur, Rp, (size_t)n * sizeof(int));
    for (long k = 0; k < M->nnz; k++) Ri[cur[M->row[k] - 1]++] = M->col[k] - 1;
    free(cur);
    for (int i = 0; i < n; i++) {                               /* 行内排序，便于去重 */
        int lo = Rp[i], hi = Rp[i + 1];
        for (int a = lo + 1; a < hi; a++) {
            int key = Ri[a], b = a - 1;
            while (b >= lo && Ri[b] > key) { Ri[b + 1] = Ri[b]; b--; }
            Ri[b + 1] = key;
        }
    }
    /* 2) A'A 模式：对每行内的列两两配对 */
    long cap = (long)M->nnz * 8 + 64, cnt_all = 0;
    int *Cp = (int *)calloc((size_t)n + 1, sizeof(int));
    int **list = (int **)calloc((size_t)n, sizeof(int *));
    int *len  = (int *)calloc((size_t)n, sizeof(int));
    int *capc = (int *)calloc((size_t)n, sizeof(int));
    int *mark = (int *)malloc((size_t)n * sizeof(int));
    for (int i = 0; i < n; i++) mark[i] = -1;
    for (int i = 0; i < n; i++) {
        for (int a = Rp[i]; a < Rp[i + 1]; a++) {
            int j = Ri[a];
            for (int b = Rp[i]; b < Rp[i + 1]; b++) {
                int kk = Ri[b];
                if (mark[kk] == j) continue;
                mark[kk] = j;
                if (len[j] == capc[j]) {
                    capc[j] = capc[j] ? capc[j] * 2 : 16;
                    list[j] = (int *)realloc(list[j], (size_t)capc[j] * sizeof(int));
                }
                list[j][len[j]++] = kk;
            }
        }
    }
    (void)cap; (void)cnt_all;
    /* 3) 每列排序（AMD 要求） */
    for (int j = 0; j < n; j++) {
        int *v = list[j], m = len[j];
        for (int a = 1; a < m; a++) {
            int key = v[a], b = a - 1;
            while (b >= 0 && v[b] > key) { v[b + 1] = v[b]; b--; }
            v[b + 1] = key;
        }
        Cp[j] = m;                              /* 先存每列长度，后面前缀和 */
    }
    long tot = 0;
    for (int j = 0; j < n; j++) tot += Cp[j];
    int *Ap2 = (int *)calloc((size_t)n + 1, sizeof(int));
    int *Ai2 = (int *)malloc((size_t)tot * sizeof(int));
    long p = 0;
    for (int j = 0; j < n; j++) {
        Ap2[j] = (int)p;
        for (int a = 0; a < len[j]; a++) Ai2[p++] = list[j][a];
        free(list[j]);
    }
    Ap2[n] = (int)p;
    free(list); free(len); free(capc); free(mark);

    int *P = (int *)malloc((size_t)n * sizeof(int));
    int st = amd_order(n, Ap2, Ai2, P, NULL, NULL);
    free(Ap2); free(Ai2); free(Cp); free(Rp); free(Ri);
    /* AMD_OK=0，AMD_OK_BUT_JUMBLED=1（列有序但有重复/未排序，P 仍然有效） */
    if (st != 0 && st != 1) { fprintf(stderr, "amd_order status=%d\n", st); free(P); return 1; }
    *q_out = P;                                  /* P[i] = 第 i 个新列对应的旧列 */
    return 0;
}

/* ---- A12：用 KLU 的 AMD 分析得到列序（与 KLU 基线同序，用于隔离"排序 vs 内核"）---- */
static int run_klu_amd(const s0mat *M, int **q_out)
{
    int n = M->n;
    int *Ap, *Ai; double *Ax;
    build_csc_q(M, NULL, &Ap, &Ai, &Ax, NULL);
    klu_common C;
    if (!klu_defaults(&C)) { fprintf(stderr, "klu_defaults fail\n"); return 1; }
    C.btf = 0; C.ordering = 0; C.scale = 2; C.tol = 0.001;   /* 0 = AMD */
    klu_symbolic *S = klu_analyze(n, Ap, Ai, &C);
    if (!S) { fprintf(stderr, "klu_analyze fail\n"); free(Ap); free(Ai); free(Ax); return 1; }
    *q_out = (int *)malloc((size_t)n * sizeof(int));
    for (int j = 0; j < n; j++) (*q_out)[j] = (int)S->Q[j];
    klu_free_symbolic(&S, &C);
    free(Ap); free(Ai); free(Ax);
    return 0;
}

static void build_csc_q(const s0mat *M, const int *q,
                        int **Ap_out, int **Ai_out, double **Ax_out,
                        int **diagrow_out)
{
    int n = M->n;
    int *invq = NULL;
    if (q) {
        invq = (int *)malloc((size_t)n * sizeof(int));
        for (int j = 0; j < n; j++) invq[q[j]] = j;
    }
    int *Ap = (int *)calloc((size_t)n + 1, sizeof(int));
    for (int i = 0; i < M->nnz; i++) {
        int old_c = M->col[i] - 1;
        int c = q ? invq[old_c] : old_c;
        if (c >= 0 && c < n) Ap[c + 1]++;
    }
    for (int i = 0; i < n; i++) Ap[i + 1] += Ap[i];
    int *Ai = (int *)malloc((size_t)M->nnz * sizeof(int));
    double *Ax = (double *)malloc((size_t)M->nnz * sizeof(double));
    int *cur = (int *)malloc((size_t)n * sizeof(int));
    memcpy(cur, Ap, (size_t)n * sizeof(int));
    for (int i = 0; i < M->nnz; i++) {
        int old_c = M->col[i] - 1;
        int c = q ? invq[old_c] : old_c;
        int p = cur[c]++;
        Ai[p] = M->row[i] - 1;
        Ax[p] = M->val[i];
    }
    free(cur);
    if (invq) free(invq);
    *Ap_out = Ap; *Ai_out = Ai; *Ax_out = Ax;
    if (diagrow_out) {
        int *dg = (int *)malloc((size_t)n * sizeof(int));
        for (int k = 0; k < n; k++) dg[k] = q ? q[k] : k;
        *diagrow_out = dg;
    }
}

static double residual(const s0mat *M, const double *x)
{
    double num = 0, den = 0;
    double *bh = (double *)calloc((size_t)M->n, sizeof(double));
    for (int i = 0; i < M->nnz; i++) {
        int r = M->row[i] - 1, c = M->col[i] - 1;
        bh[r] += M->val[i] * x[c];
    }
    for (int i = 0; i < M->n; i++) {
        double d = bh[i] - M->b[i + 1];
        num += d * d;
        den += M->b[i + 1] * M->b[i + 1];
    }
    free(bh);
    return sqrt(num / den);
}

static void matvec(const s0mat *M, const double *x, double *y)
{
    for (int i = 0; i < M->n; i++) y[i] = 0.0;
    for (int k = 0; k < M->nnz; k++)
        y[M->row[k] - 1] += M->val[k] * x[M->col[k] - 1];
}

static double rel_l2(int n, const double *a, const double *b)
{
    double num = 0, den = 0;
    for (int i = 0; i < n; i++) {
        double d = a[i] - b[i];
        num += d * d;
        den += b[i] * b[i];
    }
    return sqrt(num / den);
}

/* warmup 1 次 + reps 次，取最优（min）——cudaEvent 内核级计时 */
template <typename F>
static double time_best(F&& f, int reps)
{
    cudaEvent_t e0, e1;
    CK(cudaEventCreate(&e0));
    CK(cudaEventCreate(&e1));
    f();   /* warmup */
    double best = 1e300;
    for (int r = 0; r < reps; r++) {
        CK(cudaEventRecord(e0));
        f();
        CK(cudaEventRecord(e1));
        CK(cudaDeviceSynchronize());
        float ms = 0;
        CK(cudaEventElapsedTime(&ms, e0, e1));
        if (ms < best) best = ms;
    }
    CK(cudaEventDestroy(e0));
    CK(cudaEventDestroy(e1));
    return best;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <s0.mtx> <s0.rhs> [pin] [flt] [max_n_st] [reps]\n", argv[0]);
        return 2;
    }
    s0mat M;
    if (read_s0(argv[1], argv[2], &M)) return 1;
    double pin_val = (argc >= 4) ? atof(argv[3]) : 0.0;
    const char *flt = (argc >= 5) ? argv[4] : NULL;
    int max_n_st = (argc >= 6) ? atoi(argv[5]) : 15000;
    int reps = (argc >= 7) ? atoi(argv[6]) : 0;
    if (reps <= 0) reps = 5;
    int st_reps = 2;
    if (getenv("DSH_ST_REPS")) st_reps = atoi(getenv("DSH_ST_REPS"));
    if (st_reps < 1) st_reps = 1;
    const int skip_par = getenv("DSH_SKIP_PAR") ? 1 : 0;   /* n 过大时并行因子超共享内存上限 */

    printf("== mp_lu_bench %s ==\nn=%d nnz=%d pin=%.1e flt=%s max_n_st=%d reps=%d\n",
           argv[1], M.n, M.nnz, pin_val, flt ? flt : "-", max_n_st, reps);

    apply_flt_pin(&M, flt, pin_val);

    int *q = NULL;
    const char *ord_env = getenv("DSH_ORDER");
    int use_amd = (ord_env && strcmp(ord_env, "klu_amd") == 0);
    int use_amd_ata = (ord_env && strcmp(ord_env, "amd_ata") == 0);
    if (use_amd) {
        if (run_klu_amd(&M, &q)) return 1;
        printf("klu_amd ok\n");
    } else if (use_amd_ata) {
        if (run_amd_ata(&M, &q)) return 1;
        printf("amd_ata ok\n");
    } else {
        if (run_colamd(&M, &q)) return 1;
        printf("colamd ok\n");
    }

    int *Ap, *Ai, *diagrow;
    double *Ax;
    build_csc_q(&M, q, &Ap, &Ai, &Ax, &diagrow);
    int n = M.n;

    /* ---- CPU 参考（fp64，同序）：给因子容量 + 正确性对照 ---- */
    double *x_cpu = (double *)malloc((size_t)n * sizeof(double));
    long lnnz_cpu = 0, unnz_cpu = 0;
    {
        int *Ap0, *Ai0; double *Ax0;
        build_csc_q(&M, NULL, &Ap0, &Ai0, &Ax0, NULL);
        int rc = cpu_lu_ref(n, Ap0, Ai0, Ax0, q, M.b + 1, 1.0, x_cpu, &lnnz_cpu, &unnz_cpu);
        free(Ap0); free(Ai0); free(Ax0);
        if (rc >= 0) { fprintf(stderr, "CPU reference singular at column %d\n", rc); return 1; }
    }
    printf("CPU ref: lnnz=%ld unnz=%ld (L+U=%ld)\n", lnnz_cpu, unnz_cpu, lnnz_cpu + unnz_cpu);

    long Lcap = 2L * M.nnz + 64;
    long Ucap = 2L * M.nnz + 64;
    if (lnnz_cpu > Lcap) Lcap = (long)(lnnz_cpu * 1.5) + 64;
    if (unnz_cpu > Ucap) Ucap = (long)(unnz_cpu * 1.5) + 64;

    /* ---- GPU 分配 ---- */
    int *d_Ap, *d_Ai, *d_diag, *d_q;
    double *d_Ax;
    int *d_Lp, *d_Li, *d_Up, *d_Ui;
    double *d_Lx, *d_Ux;
    int *d_pinv, *d_xi, *d_xip, *d_lnnz, *d_unnz, *d_sing;
    double *d_x, *d_b, *d_xo, *d_wd;
    int *d_wi;
    int *d_Lp32, *d_Up32, *d_pinv32, *d_xi32;
    float *d_Ax32, *d_Lx32, *d_Ux32, *d_x32;

    CK(cudaMalloc((void **)&d_Ap, (n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_Ai, (size_t)M.nnz * sizeof(int)));
    CK(cudaMalloc((void **)&d_Ax, (size_t)M.nnz * sizeof(double)));
    CK(cudaMalloc((void **)&d_Ax32, (size_t)M.nnz * sizeof(float)));
    CK(cudaMalloc((void **)&d_diag, (size_t)n * sizeof(int)));
    CK(cudaMalloc((void **)&d_q, (size_t)n * sizeof(int)));
    CK(cudaMalloc((void **)&d_Lp, (n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_Li, (size_t)Lcap * sizeof(int)));
    CK(cudaMalloc((void **)&d_Lx, (size_t)Lcap * sizeof(double)));
    CK(cudaMalloc((void **)&d_Up, (n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_Ui, (size_t)Ucap * sizeof(int)));
    CK(cudaMalloc((void **)&d_Ux, (size_t)Ucap * sizeof(double)));
    CK(cudaMalloc((void **)&d_Lp32, (n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_Lx32, (size_t)Lcap * sizeof(float)));
    CK(cudaMalloc((void **)&d_Up32, (n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_Ux32, (size_t)Ucap * sizeof(float)));
    CK(cudaMalloc((void **)&d_pinv, (size_t)n * sizeof(int)));
    CK(cudaMalloc((void **)&d_pinv32, (size_t)n * sizeof(int)));
    CK(cudaMalloc((void **)&d_xi, (size_t)(2 * n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_xi32, (size_t)(2 * n + 1) * sizeof(int)));
    CK(cudaMalloc((void **)&d_xip, (size_t)(n + 4 * LU_PAR_CAP) * sizeof(int)));
    CK(cudaMalloc((void **)&d_x, (size_t)n * sizeof(double)));
    CK(cudaMalloc((void **)&d_x32, (size_t)n * sizeof(float)));
    CK(cudaMalloc((void **)&d_b, (size_t)n * sizeof(double)));
    CK(cudaMalloc((void **)&d_xo, (size_t)n * sizeof(double)));
    CK(cudaMalloc((void **)&d_wi, (size_t)n * sizeof(int)));
    CK(cudaMalloc((void **)&d_wd, (size_t)(2 * n) * sizeof(double)));
    CK(cudaMalloc((void **)&d_lnnz, sizeof(int)));
    CK(cudaMalloc((void **)&d_unnz, sizeof(int)));
    CK(cudaMalloc((void **)&d_sing, sizeof(int)));

    CK(cudaMemcpy(d_Ap, Ap, (n + 1) * sizeof(int), cudaMemcpyHostToDevice));
    CK(cudaMemcpy(d_Ai, Ai, (size_t)M.nnz * sizeof(int), cudaMemcpyHostToDevice));
    CK(cudaMemcpy(d_Ax, Ax, (size_t)M.nnz * sizeof(double), cudaMemcpyHostToDevice));
    float *Ax32 = (float *)malloc((size_t)M.nnz * sizeof(float));
    for (int i = 0; i < M.nnz; i++) Ax32[i] = (float)Ax[i];
    CK(cudaMemcpy(d_Ax32, Ax32, (size_t)M.nnz * sizeof(float), cudaMemcpyHostToDevice));
    CK(cudaMemcpy(d_diag, diagrow, (size_t)n * sizeof(int), cudaMemcpyHostToDevice));
    CK(cudaMemcpy(d_q, q, (size_t)n * sizeof(int), cudaMemcpyHostToDevice));
    CK(cudaMemcpy(d_b, M.b + 1, (size_t)n * sizeof(double), cudaMemcpyHostToDevice));

    /* 并行 factor 动态共享内存属性 */
    if (!skip_par) {
        size_t shb = LU_PAR_SHARED_BYTES(n);
        if (shb > 48 * 1024)
            CK(cudaFuncSetAttribute(lu_factor_par_kernel,
                cudaFuncAttributeMaxDynamicSharedMemorySize, (int)shb));
    }

    int do_st = (n <= max_n_st);

    /* ---- 读取因子状态辅助 ---- */
    auto read_status = [&](const char *tag) {
        int sing = 0, lnnz = 0, unnz = 0;
        CK(cudaMemcpy(&sing, d_sing, sizeof(int), cudaMemcpyDeviceToHost));
        CK(cudaMemcpy(&lnnz, d_lnnz, sizeof(int), cudaMemcpyDeviceToHost));
        CK(cudaMemcpy(&unnz, d_unnz, sizeof(int), cudaMemcpyDeviceToHost));
        if (sing == -2) { fprintf(stderr, "[%s] capacity overflow\n", tag); exit(1); }
        if (sing == -3) { fprintf(stderr, "[%s] structure overflow (frontier/jlist)\n", tag); exit(1); }
        if (sing >= 0)  { fprintf(stderr, "[%s] singular at column %d\n", tag, sing); exit(1); }
        return std::pair<int,int>(lnnz, unnz);
    };

    auto download_xo = [&]() {
        double *h = (double *)malloc((size_t)n * sizeof(double));
        CK(cudaMemcpy(h, d_xo, (size_t)n * sizeof(double), cudaMemcpyDeviceToHost));
        return h;
    };

    double t_f_st64 = -1, t_f_st32 = -1, t_f_par64 = -1;
    double t_t_st64 = -1, t_t_st32 = -1, t_t_par64 = -1, t_t_par32 = -1;
    long lnnz64 = -1, unnz64 = -1, lnnz32 = -1, unnz32 = -1;

    /* ============ 1) fp64 单 thread 因子 + 三角求解 ============ */
    if (do_st) {
        auto fac = [&]() {
            lu_factor_kernel<<<1, 1>>>(n, d_Ap, d_Ai, d_Ax, d_diag,
                d_Lp, d_Li, d_Lx, Lcap, d_Up, d_Ui, d_Ux, Ucap,
                d_pinv, d_xi, d_x, d_lnnz, d_unnz, d_sing);
            CK(cudaGetLastError());
        };
        auto sol = [&]() {
            trisolve_kernel<<<1, 1>>>(n, d_Lp, d_Li, d_Lx, d_Up, d_Ui, d_Ux,
                d_pinv, d_q, d_b, d_xo, d_wi, d_wd);
            CK(cudaGetLastError());
        };
        fac();  read_status("fp64 ST factor");
        auto p = read_status("fp64 ST factor");
        lnnz64 = p.first; unnz64 = p.second;
        t_f_st64 = time_best(fac, st_reps);
        t_t_st64 = time_best(sol, reps);
        double *h = download_xo();
        printf("fp64 ST: factor=%.3f ms trisolve=%.3f ms  L2(vs CPU)=%.3e res=%.3e\n",
               t_f_st64, t_t_st64, rel_l2(n, h, x_cpu), residual(&M, h));
        free(h);
    }

    /* ============ 2) fp32 单 thread 因子 + 三角求解 ============ */
    if (do_st) {
        auto fac = [&]() {
            lu_factor_f32_kernel<<<1, 1>>>(n, d_Ap, d_Ai, d_Ax32, d_diag,
                d_Lp32, d_Li, d_Lx32, Lcap, d_Up32, d_Ui, d_Ux32, Ucap,
                d_pinv32, d_xi32, d_x32, d_lnnz, d_unnz, d_sing);
            CK(cudaGetLastError());
        };
        auto sol = [&]() {
            trisolve_f32_kernel<<<1, 1>>>(n, d_Lp32, d_Li, d_Lx32, d_Up32, d_Ui, d_Ux32,
                d_pinv32, d_q, d_b, d_xo, d_wi, d_wd);
            CK(cudaGetLastError());
        };
        fac(); read_status("fp32 ST factor");
        auto p = read_status("fp32 ST factor");
        lnnz32 = p.first; unnz32 = p.second;
        t_f_st32 = time_best(fac, st_reps);
        t_t_st32 = time_best(sol, reps);
        double *h = download_xo();
        printf("fp32 ST: factor=%.3f ms trisolve=%.3f ms  L2(vs CPU)=%.3e res=%.3e\n",
               t_f_st32, t_t_st32, rel_l2(n, h, x_cpu), residual(&M, h));
        free(h);
    }

    /* ============ 3) fp64 并行因子 + 并行三角求解 ============ */
    if (!skip_par) {
        auto fac = [&]() {
            lu_factor_par_kernel<<<1, 256, LU_PAR_SHARED_BYTES(n)>>>(
                n, d_Ap, d_Ai, d_Ax, d_diag,
                d_Lp, d_Li, d_Lx, Lcap, d_Up, d_Ui, d_Ux, Ucap,
                d_pinv, d_xip, NULL, d_lnnz, d_unnz, d_sing);
            CK(cudaGetLastError());
        };
        auto sol = [&]() {
            trisolve_par_kernel<<<1, 256>>>(n, d_Lp, d_Li, d_Lx, d_Up, d_Ui, d_Ux,
                d_pinv, d_q, d_b, d_xo, d_wi, d_wd);
            CK(cudaGetLastError());
        };
        fac(); read_status("fp64 PAR factor");
        auto p = read_status("fp64 PAR factor");
        lnnz64 = p.first; unnz64 = p.second;
        t_f_par64 = time_best(fac, reps);
        t_t_par64 = time_best(sol, reps);
        double *h = download_xo();
        printf("fp64 PAR: factor=%.3f ms trisolve=%.3f ms  L2(vs CPU)=%.3e res=%.3e\n",
               t_f_par64, t_t_par64, rel_l2(n, h, x_cpu), residual(&M, h));
        free(h);
    }

    /* ============ 4) fp32 并行三角求解（用 fp32 ST 因子） ============ */
    if (!skip_par && t_f_st32 >= 0) {
        auto fac = [&]() {
            lu_factor_f32_kernel<<<1, 1>>>(n, d_Ap, d_Ai, d_Ax32, d_diag,
                d_Lp32, d_Li, d_Lx32, Lcap, d_Up32, d_Ui, d_Ux32, Ucap,
                d_pinv32, d_xi32, d_x32, d_lnnz, d_unnz, d_sing);
            CK(cudaGetLastError());
        };
        auto sol = [&]() {
            trisolve_par_f32_kernel<<<1, 256>>>(n, d_Lp32, d_Li, d_Lx32, d_Up32, d_Ui, d_Ux32,
                d_pinv32, d_q, d_b, d_xo, d_wi, d_wd);
            CK(cudaGetLastError());
        };
        fac(); read_status("fp32 PAR trisolve factor");
        t_t_par32 = time_best(sol, reps);
        double *h = download_xo();
        printf("fp32 PAR trisolve: %.3f ms  L2(vs CPU)=%.3e res=%.3e\n",
               t_t_par32, rel_l2(n, h, x_cpu), residual(&M, h));
        free(h);
    } else {
        printf("fp32 PAR trisolve: n/a (fp32 ST factor skipped at n>%d)\n", max_n_st);
    }

    /* ============ 5) A1: 迭代精化（fp32 因子 / fp64 因子两套） ============ */
    int    ir32_iters = 0, ir64_iters = 0;
    double ir32_total = -1, ir32_res = -1, ir64_total = -1, ir64_res = -1;
    const int    ir_maxit = getenv("DSH_IR_MAXIT") ? atoi(getenv("DSH_IR_MAXIT")) : 20;
    const double ir_tol   = getenv("DSH_IR_TOL")   ? atof(getenv("DSH_IR_TOL"))   : 1e-10;

    if (getenv("DSH_IR")) {
        double normb = 0.0;
        for (int i = 0; i < n; i++) normb += M.b[i + 1] * M.b[i + 1];
        normb = sqrt(normb);

        double *d_brhs;
        CK(cudaMalloc((void **)&d_brhs, (size_t)n * sizeof(double)));
        double *hx = (double *)calloc((size_t)n, sizeof(double));
        double *hr = (double *)malloc((size_t)n * sizeof(double));
        double *hd = (double *)malloc((size_t)n * sizeof(double));
        double *hay = (double *)malloc((size_t)n * sizeof(double));

        /* ---- 5a) fp32 因子 + fp64 残差 ---- */
        if (t_f_st32 >= 0) {
            auto fac32 = [&]() {
                lu_factor_f32_kernel<<<1, 1>>>(n, d_Ap, d_Ai, d_Ax32, d_diag,
                    d_Lp32, d_Li, d_Lx32, Lcap, d_Up32, d_Ui, d_Ux32, Ucap,
                    d_pinv32, d_xi32, d_x32, d_lnnz, d_unnz, d_sing);
                CK(cudaGetLastError());
            };
            auto sol32 = [&]() {
                trisolve_par_f32_kernel<<<1, 256>>>(n, d_Lp32, d_Li, d_Lx32, d_Up32, d_Ui, d_Ux32,
                    d_pinv32, d_q, d_brhs, d_xo, d_wi, d_wd);
                CK(cudaGetLastError());
            };
            fac32(); read_status("IR fp32 factor");
            for (int i = 0; i < n; i++) hx[i] = 0.0;
            memcpy(hr, M.b + 1, (size_t)n * sizeof(double));
            double tri = 0, spmv = 0;
            int it = 0;
            for (; it < ir_maxit; it++) {
                double nr = 0.0;
                for (int i = 0; i < n; i++) nr += hr[i] * hr[i];
                nr = sqrt(nr) / normb;
                if (!(nr == nr) || nr > 1e8 || nr < ir_tol) break;
                CK(cudaMemcpy(d_brhs, hr, (size_t)n * sizeof(double), cudaMemcpyHostToDevice));
                tri += time_best(sol32, 1);
                CK(cudaMemcpy(hd, d_xo, (size_t)n * sizeof(double), cudaMemcpyDeviceToHost));
                for (int i = 0; i < n; i++) hx[i] += hd[i];
                struct timespec a0, a1;
                clock_gettime(CLOCK_MONOTONIC, &a0);
                matvec(&M, hx, hay);
                for (int i = 0; i < n; i++) hr[i] = M.b[i + 1] - hay[i];
                clock_gettime(CLOCK_MONOTONIC, &a1);
                spmv += (a1.tv_sec - a0.tv_sec) * 1e3 + (a1.tv_nsec - a0.tv_nsec) / 1e6;
            }
            ir32_iters = it; ir32_total = tri + spmv; ir32_res = residual(&M, hx);
            printf("fp32 IR: iters=%d tri=%.3f ms spmv=%.3f ms total=%.3f ms  res=%.3e\n",
                   ir32_iters, tri, spmv, ir32_total, ir32_res);
        } else {
            printf("fp32 IR: n/a (fp32 ST factor skipped at n>%d)\n", max_n_st);
        }

        /* ---- 5b) fp64 因子（并行）+ fp64 残差 ---- */
        if (!skip_par) {
            auto fac64 = [&]() {
                lu_factor_par_kernel<<<1, 256, LU_PAR_SHARED_BYTES(n)>>>(
                    n, d_Ap, d_Ai, d_Ax, d_diag,
                    d_Lp, d_Li, d_Lx, Lcap, d_Up, d_Ui, d_Ux, Ucap,
                    d_pinv, d_xip, NULL, d_lnnz, d_unnz, d_sing);
                CK(cudaGetLastError());
            };
            auto sol64 = [&]() {
                trisolve_par_kernel<<<1, 256>>>(n, d_Lp, d_Li, d_Lx, d_Up, d_Ui, d_Ux,
                    d_pinv, d_q, d_brhs, d_xo, d_wi, d_wd);
                CK(cudaGetLastError());
            };
            fac64(); read_status("IR fp64 PAR factor");
            for (int i = 0; i < n; i++) hx[i] = 0.0;
            memcpy(hr, M.b + 1, (size_t)n * sizeof(double));
            double tri = 0, spmv = 0;
            int it = 0;
            for (; it < ir_maxit; it++) {
                double nr = 0.0;
                for (int i = 0; i < n; i++) nr += hr[i] * hr[i];
                nr = sqrt(nr) / normb;
                if (!(nr == nr) || nr > 1e8 || nr < ir_tol) break;
                CK(cudaMemcpy(d_brhs, hr, (size_t)n * sizeof(double), cudaMemcpyHostToDevice));
                tri += time_best(sol64, 1);
                CK(cudaMemcpy(hd, d_xo, (size_t)n * sizeof(double), cudaMemcpyDeviceToHost));
                for (int i = 0; i < n; i++) hx[i] += hd[i];
                struct timespec a0, a1;
                clock_gettime(CLOCK_MONOTONIC, &a0);
                matvec(&M, hx, hay);
                for (int i = 0; i < n; i++) hr[i] = M.b[i + 1] - hay[i];
                clock_gettime(CLOCK_MONOTONIC, &a1);
                spmv += (a1.tv_sec - a0.tv_sec) * 1e3 + (a1.tv_nsec - a0.tv_nsec) / 1e6;
            }
            ir64_iters = it; ir64_total = tri + spmv; ir64_res = residual(&M, hx);
            printf("fp64 IR: iters=%d tri=%.3f ms spmv=%.3f ms total=%.3f ms  res=%.3e\n",
                   ir64_iters, tri, spmv, ir64_total, ir64_res);
        }

        free(hx); free(hr); free(hd); free(hay);
        CK(cudaFree(d_brhs));
    }

    /* ============ 6) A13: GMRES-IR（右预条件，m=50，最多 7 次 restart） ============ */
    int    gm32_iters = 0, gm64_iters = 0;
    double gm32_ms = -1, gm32_res = -1, gm64_ms = -1, gm64_res = -1;
    if (getenv("DSH_GMRES")) {
        const int    m         = 50;
        const int    max_outer = 7;
        const double tol       = getenv("DSH_IR_TOL") ? atof(getenv("DSH_IR_TOL")) : 1e-10;

        double *d_bg, *d_xg;
        CK(cudaMalloc((void **)&d_bg, (size_t)n * sizeof(double)));
        CK(cudaMalloc((void **)&d_xg, (size_t)n * sizeof(double)));

        double **V = (double **)malloc((size_t)(m + 1) * sizeof(double *));
        for (int i = 0; i <= m; i++) V[i] = (double *)malloc((size_t)n * sizeof(double));
        double *H  = (double *)calloc((size_t)(m + 1) * m, sizeof(double));
        double *cs = (double *)calloc((size_t)m, sizeof(double));
        double *sn = (double *)calloc((size_t)m, sizeof(double));
        double *g  = (double *)calloc((size_t)(m + 1), sizeof(double));
        double *w  = (double *)malloc((size_t)n * sizeof(double));
        double *z  = (double *)malloc((size_t)n * sizeof(double));
        double *r0 = (double *)malloc((size_t)n * sizeof(double));
        double *xc = (double *)calloc((size_t)n, sizeof(double));

        double normb = 0.0;
        for (int i = 0; i < n; i++) normb += M.b[i + 1] * M.b[i + 1];
        normb = sqrt(normb);

        for (int use32 = 0; use32 <= 1; use32++) {
            if (use32 && t_f_st32 < 0) { printf("gmres32: n/a\n"); continue; }
            /* 建因子 */
            if (use32) {
                lu_factor_f32_kernel<<<1, 1>>>(n, d_Ap, d_Ai, d_Ax32, d_diag,
                    d_Lp32, d_Li, d_Lx32, Lcap, d_Up32, d_Ui, d_Ux32, Ucap,
                    d_pinv32, d_xi32, d_x32, d_lnnz, d_unnz, d_sing);
                CK(cudaGetLastError());
            } else {
                lu_factor_par_kernel<<<1, 256, LU_PAR_SHARED_BYTES(n)>>>(
                    n, d_Ap, d_Ai, d_Ax, d_diag,
                    d_Lp, d_Li, d_Lx, Lcap, d_Up, d_Ui, d_Ux, Ucap,
                    d_pinv, d_xip, NULL, d_lnnz, d_unnz, d_sing);
                CK(cudaGetLastError());
            }
            read_status(use32 ? "gmres fp32 factor" : "gmres fp64 factor");

            /* M^-1 作用一次（CPU 侧接口） */
            auto prec = [&](const double *in, double *out) {
                CK(cudaMemcpy(d_bg, in, (size_t)n * sizeof(double), cudaMemcpyHostToDevice));
                if (use32)
                    trisolve_par_f32_kernel<<<1, 256>>>(n, d_Lp32, d_Li, d_Lx32, d_Up32, d_Ui, d_Ux32,
                        d_pinv32, d_q, d_bg, d_xg, d_wi, d_wd);
                else
                    trisolve_par_kernel<<<1, 256>>>(n, d_Lp, d_Li, d_Lx, d_Up, d_Ui, d_Ux,
                        d_pinv, d_q, d_bg, d_xg, d_wi, d_wd);
                CK(cudaGetLastError());
                CK(cudaDeviceSynchronize());
                CK(cudaMemcpy(out, d_xg, (size_t)n * sizeof(double), cudaMemcpyDeviceToHost));
            };

            struct timespec t0, t1;
            clock_gettime(CLOCK_MONOTONIC, &t0);
            memset(xc, 0, (size_t)n * sizeof(double));
            int total = 0;
            double rel = 1.0;
            for (int outer = 0; outer < max_outer; outer++) {
                double beta = 0.0;
                for (int i = 0; i < n; i++) r0[i] = M.b[i + 1];
                for (long kk = 0; kk < M.nnz; kk++)
                    r0[M.row[kk] - 1] -= M.val[kk] * xc[M.col[kk] - 1];
                for (int i = 0; i < n; i++) beta += r0[i] * r0[i];
                beta = sqrt(beta);
                rel = beta / normb;
                if (rel <= tol) break;
                for (int i = 0; i < n; i++) V[0][i] = r0[i] / beta;
                memset(H, 0, (size_t)(m + 1) * m * sizeof(double));
                memset(g, 0, (size_t)(m + 1) * sizeof(double));
                g[0] = beta;
                int j = 0;
                for (j = 0; j < m; j++) {
                    prec(V[j], z);
                    for (int i = 0; i < n; i++) w[i] = 0.0;
                    for (long kk = 0; kk < M.nnz; kk++)
                        w[M.row[kk] - 1] += M.val[kk] * z[M.col[kk] - 1];
                    for (int pass = 0; pass < 2; pass++)
                        for (int i = 0; i <= j; i++) {
                            double h = 0.0;
                            for (int t = 0; t < n; t++) h += V[i][t] * w[t];
                            H[i * m + j] += h;
                            for (int t = 0; t < n; t++) w[t] -= h * V[i][t];
                        }
                    double hn = 0.0;
                    for (int t = 0; t < n; t++) hn += w[t] * w[t];
                    hn = sqrt(hn);
                    if (hn < 1e-14) { j++; break; }
                    H[(j + 1) * m + j] = hn;
                    for (int t = 0; t < n; t++) V[j + 1][t] = w[t] / hn;
                    for (int i = 0; i < j; i++) {
                        double tt = H[i * m + j];
                        H[i * m + j] = cs[i] * tt + sn[i] * H[(i + 1) * m + j];
                        H[(i + 1) * m + j] = -sn[i] * tt + cs[i] * H[(i + 1) * m + j];
                    }
                    double t1v = H[j * m + j], t2v = H[(j + 1) * m + j];
                    double rr = sqrt(t1v * t1v + t2v * t2v);
                    if (rr == 0.0) { j++; break; }
                    cs[j] = t1v / rr; sn[j] = t2v / rr;
                    H[j * m + j] = rr; H[(j + 1) * m + j] = 0.0;
                    g[j + 1] = -sn[j] * g[j];
                    g[j] = cs[j] * g[j];
                    if (fabs(g[j + 1]) / normb <= tol) { j++; break; }
                }
                total += j;
                double *y = (double *)calloc((size_t)j, sizeof(double));
                for (int i = j - 1; i >= 0; i--) {
                    double sum = g[i];
                    for (int t = i + 1; t < j; t++) sum -= H[i * m + t] * y[t];
                    y[i] = sum / H[i * m + i];
                }
                for (int t = 0; t < n; t++) z[t] = 0.0;
                for (int kk = 0; kk < j; kk++)
                    for (int t = 0; t < n; t++) z[t] += y[kk] * V[kk][t];
                double *dz = (double *)malloc((size_t)n * sizeof(double));
                prec(z, dz);
                for (int t = 0; t < n; t++) xc[t] += dz[t];
                free(dz); free(y);
                double nr = 0.0;
                for (int t = 0; t < n; t++) r0[t] = M.b[t + 1];
                for (long kk = 0; kk < M.nnz; kk++)
                    r0[M.row[kk] - 1] -= M.val[kk] * xc[M.col[kk] - 1];
                for (int t = 0; t < n; t++) nr += r0[t] * r0[t];
                rel = sqrt(nr) / normb;
                if (rel <= tol) break;
            }
            clock_gettime(CLOCK_MONOTONIC, &t1);
            double ms = (t1.tv_sec - t0.tv_sec) * 1e3 + (t1.tv_nsec - t0.tv_nsec) / 1e6;
            double rr = residual(&M, xc);
            if (use32) { gm32_iters = total; gm32_ms = ms; gm32_res = rr; }
            else       { gm64_iters = total; gm64_ms = ms; gm64_res = rr; }
            printf("gmres%s: iters=%d total=%.3f ms  res=%.3e (tol=%.0e)\n",
                   use32 ? "32" : "64", total, ms, rr, tol);
        }
        for (int i = 0; i <= m; i++) free(V[i]);
        free(V); free(H); free(cs); free(sn); free(g); free(w); free(z); free(r0); free(xc);
        CK(cudaFree(d_bg)); CK(cudaFree(d_xg));
    }

    /* ---- 汇总 ---- */
    double l64 = lnnz64 > 0 ? (double)lnnz64 : (double)lnnz_cpu;
    double u64 = unnz64 > 0 ? (double)unnz64 : (double)unnz_cpu;
    double l32 = lnnz32 > 0 ? (double)lnnz32 : (double)lnnz_cpu;
    double u32 = unnz32 > 0 ? (double)unnz32 : (double)unnz_cpu;
    double mem64 = (l64 + u64) * 12.0;
    double mem32 = (l32 + u32) * 8.0;
    double ratio_st = (t_f_st64 > 0 && t_f_st32 > 0) ? t_f_st64 / t_f_st32 : -1;
    double ratio_ts_st = (t_t_st64 > 0 && t_t_st32 > 0) ? t_t_st64 / t_t_st32 : -1;
    double ratio_ts_par = (t_t_par64 > 0 && t_t_par32 > 0) ? t_t_par64 / t_t_par32 : -1;

    printf("\n== SUMMARY %s n=%d nnz=%d ==\n", argv[1], n, M.nnz);
    printf("JSON:{\"matrix\":\"%s\",\"n\":%d,\"nnz\":%d,\"lnnz_cpu\":%ld,\"unnz_cpu\":%ld,"
           "\"lnnz64\":%ld,\"unnz64\":%ld,\"lnnz32\":%ld,\"unnz32\":%ld,"
           "\"mem_fp64_mb\":%.3f,\"mem_fp32_mb\":%.3f,"
           "\"t_factor_st64_ms\":%.3f,\"t_factor_st32_ms\":%.3f,"
           "\"t_factor_par64_ms\":%.3f,"
           "\"t_trisolve_st64_ms\":%.3f,\"t_trisolve_st32_ms\":%.3f,"
           "\"t_trisolve_par64_ms\":%.3f,\"t_trisolve_par32_ms\":%.3f,"
           "\"speedup_factor_st\":%.3f,\"speedup_trisolve_st\":%.3f,\"speedup_trisolve_par\":%.3f,"
           "\"ir32_iters\":%d,\"ir32_ms\":%.3f,\"ir32_res\":%.3e,"
           "\"ir64_iters\":%d,\"ir64_ms\":%.3f,\"ir64_res\":%.3e,"
           "\"gm32_iters\":%d,\"gm32_ms\":%.3f,\"gm32_res\":%.3e,"
           "\"gm64_iters\":%d,\"gm64_ms\":%.3f,\"gm64_res\":%.3e}\n",
           argv[1], n, M.nnz, lnnz_cpu, unnz_cpu,
           lnnz64, unnz64, lnnz32, unnz32,
           mem64 / 1e6, mem32 / 1e6,
           t_f_st64, t_f_st32, t_f_par64,
           t_t_st64, t_t_st32, t_t_par64, t_t_par32,
           ratio_st, ratio_ts_st, ratio_ts_par,
           ir32_iters, ir32_total, ir32_res,
           ir64_iters, ir64_total, ir64_res,
           gm32_iters, gm32_ms, gm32_res,
           gm64_iters, gm64_ms, gm64_res);

    return 0;
}
