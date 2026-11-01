/* lu_bench.c -- FP32/FP64 分块 LU 吞吐基准（同一算法、同一循环，只换精度）
 *
 * 目的：测出 s = TP32 / TP64，这是代价模型里唯一的硬件参数。
 * 算法：right-looking 分块 LU（部分主元），尾块用 i-k-j 顺序的秩-b 更新。
 * 编译：cc -O3 -o lu_bench lu_bench.c -lm
 * 用法：./lu_bench [nmax] [nb]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

#define GEN_LU(TYPE, NAME)                                                     \
static double NAME(TYPE *A, int n, int nb)                                     \
{                                                                              \
    double t0 = now_s();                                                       \
    for (int k = 0; k < n; k += nb) {                                          \
        int kb = (k + nb < n) ? nb : (n - k);                                  \
        /* 1) 面板分解（含主元交换） */                                          \
        for (int j = k; j < k + kb; j++) {                                     \
            int p = j;                                                         \
            double best = fabs((double)A[j + (size_t)j * n]);                  \
            for (int i = j + 1; i < n; i++) {                                  \
                double v = fabs((double)A[i + (size_t)j * n]);                 \
                if (v > best) { best = v; p = i; }                             \
            }                                                                  \
            if (p != j) {                                                      \
                for (int c = 0; c < n; c++) {                                  \
                    TYPE tmp = A[j + (size_t)c * n];                           \
                    A[j + (size_t)c * n] = A[p + (size_t)c * n];               \
                    A[p + (size_t)c * n] = tmp;                                \
                }                                                              \
            }                                                                  \
            TYPE piv = A[j + (size_t)j * n];                                   \
            if (piv == 0) continue;                                            \
            for (int i = j + 1; i < n; i++)                                    \
                A[i + (size_t)j * n] /= piv;                                   \
            for (int c = j + 1; c < k + kb; c++) {                             \
                TYPE u = A[j + (size_t)c * n];                                 \
                TYPE *acc = &A[j + (size_t)c * n];                             \
                for (int i = j + 1; i < n; i++)                                \
                    A[i + (size_t)c * n] -= A[i + (size_t)j * n] * u;          \
                (void)acc;                                                     \
            }                                                                  \
        }                                                                      \
        if (k + kb >= n) break;                                                \
        /* 2) 尾块更新 A22 -= L21 * U12（i-k-j） */                             \
        for (int i = k + kb; i < n; i++) {                                     \
            TYPE *Ai = &A[(size_t)i * n];                                      \
            for (int kk = k; kk < k + kb; kk++) {                              \
                TYPE l = A[i + (size_t)kk * n];                                \
                if (l == 0) continue;                                          \
                TYPE *Ak = &A[(size_t)kk * n];                                 \
                for (int j = k + kb; j < n; j++)                               \
                    Ai[j] -= l * Ak[j];                                        \
            }                                                                  \
        }                                                                      \
    }                                                                          \
    return now_s() - t0;                                                       \
}

GEN_LU(double, lu_double)
GEN_LU(float,  lu_float)

static void fill(void *p, int n, int is_double)
{
    size_t nn = (size_t)n * (size_t)n;
    for (size_t i = 0; i < nn; i++) {
        double v = 2.0 + sin((double)(i % 1024));
        if (is_double) ((double *)p)[i] = v;
        else           ((float *)p)[i] = (float)v;
    }
}

int main(int argc, char **argv)
{
    int nmax = (argc > 1) ? atoi(argv[1]) : 1024;
    int nb   = (argc > 2) ? atoi(argv[2]) : 64;
    printf("# lu_bench  nb=%d\n", nb);
    printf("%6s %14s %14s %10s\n", "n", "TP64(GF/s)", "TP32(GF/s)", "s");

    for (int n = 128; n <= nmax; n *= 2) {
        double *Ad = (double *)malloc((size_t)n * n * sizeof(double));
        float  *Af = (float  *)malloc((size_t)n * n * sizeof(float));
        if (!Ad || !Af) { fprintf(stderr, "OOM n=%d\n", n); return 1; }

        fill(Ad, n, 1);
        double td = lu_double(Ad, n, nb);
        double fd = (2.0 / 3.0) * (double)n * n * n;

        fill(Af, n, 0);
        double tf = lu_float(Af, n, nb);
        double ff = (2.0 / 3.0) * (double)n * n * n;

        double tp64 = fd / td / 1e9;
        double tp32 = ff / tf / 1e9;
        printf("%6d %14.3f %14.3f %10.3f\n", n, tp64, tp32, tp32 / tp64);
        fflush(stdout);
        free(Ad); free(Af);
    }
    return 0;
}
