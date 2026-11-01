/* hcblas_bench.cu -- 用 hcBLAS 稠密 GEMM 定 P_peak
 * 编译（服务器）：
 *   H=$HOME/local-cxx
 *   htcc -O3 -std=c++14 -isystem $H/usr/include/c++/7.3.0 \
 *        -isystem $H/usr/include/c++/7.3.0/aarch64-linux-gnu \
 *        -isystem $H/usr/include/c++/7.3.0/backward \
 *        -I/opt/hpcc-3.5.3/include -o $HOME/hcblas_bench hcblas_bench.cu \
 *        -L$H/lib -lstdc++ -L/opt/hpcc-3.5.3/lib -lhcblas -lhcruntime -lm
 */
#include <hc_runtime_api.h>
#include <hcblas/hcblas.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

template <typename T>
static void bench(int n, const char *tag, int is_double)
{
    size_t nn = (size_t)n * n;
    void *A = NULL, *B = NULL, *Cc = NULL;
    size_t sz = is_double ? sizeof(double) : sizeof(float);
    hcMalloc(&A, nn * sz); hcMalloc(&B, nn * sz); hcMalloc(&Cc, nn * sz);
    if (!A || !B || !Cc) { printf("%s n=%d alloc failed\n", tag, n); return; }

    hcblasHandle_t h = NULL;
    if (hcblasCreate(&h) != 0) { printf("%s handle failed\n", tag); return; }
    T alpha = (T)1.0, beta = (T)0.0;
    double flops = 2.0 * n * n * n;
    double best = 1e9;

    for (int rep = 0; rep < 4; rep++) {
        double t0 = now_s();
        if (is_double)
            hcblasDgemm(h, HCBLAS_OP_N, HCBLAS_OP_N, n, n, n,
                        (const double *)&alpha, (const double *)A, n,
                        (const double *)B, n, (const double *)&beta, (double *)Cc, n);
        else
            hcblasSgemm(h, HCBLAS_OP_N, HCBLAS_OP_N, n, n, n,
                        (const float *)&alpha, (const float *)A, n,
                        (const float *)B, n, (const float *)&beta, (float *)Cc, n);
        hcDeviceSynchronize();
        double dt = now_s() - t0;
        if (rep && dt < best) best = dt;      /* 首轮是预热 */
    }
    printf("%-8s n=%5d  %8.2f TFLOP/s\n", tag, n, flops / best / 1e12);
    hcblasDestroy(h);
    hcFree(A); hcFree(B); hcFree(Cc);
}

int main(int argc, char **argv)
{
    int n = (argc > 1) ? atoi(argv[1]) : 4096;
    bench<float>(n, "SGEMM", 0);
    bench<double>(n, "DGEMM", 1);
    return 0;
}
