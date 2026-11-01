// ============================================================================
// bw_probe.cu — X201 峰值带宽与访存模式对照（Roofline 用的实测点）
//
// 三个内核，同一套计时：
//   copy   : b[i] = a[i]                     → 纯流式（读+写各 N 次）
//   triad  : c[i] = a[i] + s*b[i]            → 流式三数组
//   scatter: x[idx[i]] -= v[i]               → 随机散射（模拟 LU 右看更新）
// 用法: ./bw_probe [N_MB] [reps]
// 输出 JSON: 每个内核的 GB/s
// ============================================================================
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cuda_runtime.h>

#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { \
    fprintf(stderr, "CUDA FAIL %s:%d %s: %s\n", __FILE__, __LINE__, #x, \
            cudaGetErrorString(e_)); exit(1); } } while (0)

__global__ void copy_k(const double *__restrict__ a, double *__restrict__ b, long n)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    long s = (long)gridDim.x * blockDim.x;
    for (; i < n; i += s) b[i] = a[i];
}

__global__ void triad_k(const double *__restrict__ a, const double *__restrict__ b,
                        double *__restrict__ c, long n, double alpha)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    long s = (long)gridDim.x * blockDim.x;
    for (; i < n; i += s) c[i] = a[i] + alpha * b[i];
}

__global__ void scatter_k(const int *__restrict__ idx, double *__restrict__ x,
                          const double *__restrict__ v, long m)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    long s = (long)gridDim.x * blockDim.x;
    for (; i < m; i += s) x[idx[i]] -= v[i];
}

static float timeit(void (*launch)(void *), void *ctx, int reps)
{
    cudaEvent_t e0, e1;
    CK(cudaEventCreate(&e0)); CK(cudaEventCreate(&e1));
    launch(ctx);                       /* warmup */
    CK(cudaDeviceSynchronize());
    float best = 1e30f;
    for (int r = 0; r < reps; r++) {
        CK(cudaEventRecord(e0));
        launch(ctx);
        CK(cudaEventRecord(e1));
        CK(cudaDeviceSynchronize());
        float ms = 0; CK(cudaEventElapsedTime(&ms, e0, e1));
        if (ms < best) best = ms;
    }
    CK(cudaEventDestroy(e0)); CK(cudaEventDestroy(e1));
    return best;
}

struct CopyCtx { const double *a; double *b; long n; int grid; int block; };
struct TriadCtx { const double *a; const double *b; double *c; long n; double al; int grid; int block; };
struct ScatCtx { const int *idx; double *x; const double *v; long m; int grid; int block; };

static void launch_copy(void *p) { CopyCtx *c = (CopyCtx *)p; copy_k<<<c->grid, c->block>>>(c->a, c->b, c->n); }
static void launch_triad(void *p) { TriadCtx *c = (TriadCtx *)p; triad_k<<<c->grid, c->block>>>(c->a, c->b, c->c, c->n, c->al); }
static void launch_scat(void *p) { ScatCtx *c = (ScatCtx *)p; scatter_k<<<c->grid, c->block>>>(c->idx, c->x, c->v, c->m); }

int main(int argc, char **argv)
{
    long mb = (argc >= 2) ? atol(argv[1]) : 512;
    int reps = (argc >= 3) ? atoi(argv[2]) : 10;
    long n = mb * 1024L * 1024L / 8;      /* doubles */
    int block = 256, grid = 2048;

    double *a, *b, *c, *x, *v;
    int *idx;
    CK(cudaMalloc((void **)&a, n * sizeof(double)));
    CK(cudaMalloc((void **)&b, n * sizeof(double)));
    CK(cudaMalloc((void **)&c, n * sizeof(double)));
    CK(cudaMalloc((void **)&x, n * sizeof(double)));
    CK(cudaMalloc((void **)&v, n * sizeof(double)));
    CK(cudaMalloc((void **)&idx, n * sizeof(int)));
    CK(cudaMemset(a, 0, n * sizeof(double)));
    CK(cudaMemset(b, 0, n * sizeof(double)));

    /* 随机索引（在 n 范围内）——模拟散射更新的访存模式 */
    {
        int *h = (int *)malloc(n * sizeof(int));
        unsigned s = 12345u;
        for (long i = 0; i < n; i++) { s = s * 1103515245u + 12345u; h[i] = (int)((s >> 8) % (unsigned)n); }
        CK(cudaMemcpy(idx, h, n * sizeof(int), cudaMemcpyHostToDevice));
        free(h);
    }

    CopyCtx cc = { a, b, n, grid, block };
    TriadCtx tc = { a, b, c, n, 2.0, grid, block };
    ScatCtx sc = { idx, x, v, n, grid, block };

    float t_copy = timeit(launch_copy, &cc, reps);
    float t_triad = timeit(launch_triad, &tc, reps);
    float t_scat = timeit(launch_scat, &sc, reps);

    double gb_copy = 2.0 * n * 8 / (t_copy * 1e6);     /* 读+写 */
    double gb_triad = 3.0 * n * 8 / (t_triad * 1e6);   /* 两读一写 */
    double gb_scat = 2.0 * n * 8 / (t_scat * 1e6);     /* idx 读 + v 读 + x 读改写 → 近似 */

    printf("bw_probe: n=%ld doubles (%.0f MB/array)\n", n, n * 8.0 / 1048576.0);
    printf("copy   : %.3f ms  -> %8.2f GB/s\n", t_copy, gb_copy);
    printf("triad  : %.3f ms  -> %8.2f GB/s\n", t_triad, gb_triad);
    printf("scatter: %.3f ms  -> %8.2f GB/s (随机散射)\n", t_scat, gb_scat);
    printf("JSON:{\"copy_gbs\":%.2f,\"triad_gbs\":%.2f,\"scatter_gbs\":%.2f,"
           "\"copy_ms\":%.3f,\"triad_ms\":%.3f,\"scatter_ms\":%.3f}\n",
           gb_copy, gb_triad, gb_scat, t_copy, t_triad, t_scat);
    return 0;
}
