/* lu_bench_gpu.cu -- GPU 侧 s = TP32/TP64 的微基准
 *
 * 只测 LU 里 O(n^3) 的那部分（rank-b 更新 = GEMM），因为 s 就是它的吞吐比。
 * 用你们自己的 API 习惯：原生 hc_runtime_api + __global__ + hcLaunchKernel。
 *
 * 编译（在 race-worker-mx-05 上）：
 *   HT=/opt/hpcc-3.5.3/htgpu_llvm/bin/htcc
 *   $HT -O3 -std=c++14 -I/opt/hpcc-3.5.3/include \
 *       -o lu_bench_gpu lu_bench_gpu.cu -lhcrt \
 *       -gcc-toolchain /usr/lib/gcc/aarch64-linux-gnu/7.3.0
 *
 * 运行：
 *   ./lu_bench_gpu 4096
 *
 * 输出每个 n 的 FP64/FP32 GFLOP/s 与比值 s。s 取大 n 的渐近值。
 */
#include <hc_runtime_api.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>
#include <string.h>
#include <hpcc_fp16.h>

#ifndef TILE
#define TILE 32
#endif

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

/* ---------------- 填充 ---------------- */
__global__ void fill_f32(float *a, long n)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) a[i] = (float)(1.0 + (double)(i % 97) * 1e-3);
}
__global__ void fill_f64(double *a, long n)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) a[i] = 1.0 + (double)(i % 97) * 1e-3;
}

__global__ void fill_f16(__half *a, long n)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) a[i] = __float2half((float)(1.0 + (double)(i % 97) * 1e-3));
}

/* ---------------- 共享内存分块 GEMM ---------------- */
__global__ void gemm_f32(const float *A, const float *B, float *C, int n)
{
    __shared__ float As[TILE][TILE];
    __shared__ float Bs[TILE][TILE];
    int tx = threadIdx.x, ty = threadIdx.y;
    int row = blockIdx.y * TILE + ty;
    int col = blockIdx.x * TILE + tx;
    float acc = 0.0f;

    for (int t = 0; t < (n + TILE - 1) / TILE; t++) {
        int k0 = t * TILE;
        As[ty][tx] = (row < n && k0 + tx < n) ? A[(long)row * n + k0 + tx] : 0.0f;
        Bs[ty][tx] = (col < n && k0 + ty < n) ? B[(long)(k0 + ty) * n + col] : 0.0f;
        __syncthreads();
        for (int k = 0; k < TILE; k++) acc += As[ty][k] * Bs[k][tx];
        __syncthreads();
    }
    if (row < n && col < n) C[(long)row * n + col] = acc;
}

__global__ void gemm_f64(const double *A, const double *B, double *C, int n)
{
    __shared__ double As[TILE][TILE];
    __shared__ double Bs[TILE][TILE];
    int tx = threadIdx.x, ty = threadIdx.y;
    int row = blockIdx.y * TILE + ty;
    int col = blockIdx.x * TILE + tx;
    double acc = 0.0;

    for (int t = 0; t < (n + TILE - 1) / TILE; t++) {
        int k0 = t * TILE;
        As[ty][tx] = (row < n && k0 + tx < n) ? A[(long)row * n + k0 + tx] : 0.0;
        Bs[ty][tx] = (col < n && k0 + ty < n) ? B[(long)(k0 + ty) * n + col] : 0.0;
        __syncthreads();
        for (int k = 0; k < TILE; k++) acc += As[ty][k] * Bs[k][tx];
        __syncthreads();
    }
    if (row < n && col < n) C[(long)row * n + col] = acc;
}

/* 半精度存储 + FP32 累加：不依赖张量核，代表"只降存储"的混合精度路径 */
__global__ void gemm_f16(const __half *A, const __half *B, float *C, int n)
{
    __shared__ float As[TILE][TILE];
    __shared__ float Bs[TILE][TILE];
    int tx = threadIdx.x, ty = threadIdx.y;
    int row = blockIdx.y * TILE + ty;
    int col = blockIdx.x * TILE + tx;
    float acc = 0.0f;

    for (int t = 0; t < (n + TILE - 1) / TILE; t++) {
        int k0 = t * TILE;
        As[ty][tx] = (row < n && k0 + tx < n) ? __half2float(A[(long)row * n + k0 + tx]) : 0.0f;
        Bs[ty][tx] = (col < n && k0 + ty < n) ? __half2float(B[(long)(k0 + ty) * n + col]) : 0.0f;
        __syncthreads();
        for (int k = 0; k < TILE; k++) acc += As[ty][k] * Bs[k][tx];
        __syncthreads();
    }
    if (row < n && col < n) C[(long)row * n + col] = acc;
}

/* 带宽：c = a + 2b，读写共 3N 个元素 */
__global__ void stream_f32(const float *a, const float *b, float *c, long n)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + 2.0f * b[i];
}
__global__ void stream_f64(const double *a, const double *b, double *c, long n)
{
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + 2.0 * b[i];
}

/* ---------------- host ---------------- */
static void run_case(int n)
{
    size_t nn = (size_t)n * (size_t)n;
    double flops = 2.0 * (double)n * (double)n * (double)n;
    dim3 block(TILE, TILE);
    dim3 grid((n + TILE - 1) / TILE, (n + TILE - 1) / TILE);

    float *Af = NULL, *Bf = NULL, *Cf = NULL;
    double *Ad = NULL, *Bd = NULL, *Cd = NULL;
    hcMalloc((void **)&Af, nn * sizeof(float));
    hcMalloc((void **)&Bf, nn * sizeof(float));
    hcMalloc((void **)&Cf, nn * sizeof(float));
    hcMalloc((void **)&Ad, nn * sizeof(double));
    hcMalloc((void **)&Bd, nn * sizeof(double));
    hcMalloc((void **)&Cd, nn * sizeof(double));
    if (!Af || !Ad) { printf("  n=%d alloc failed\n", n); return; }

    long total = (long)nn;
    int tb = 256, gb = (int)((total + tb - 1) / tb);
    { void *a[] = {&Af, &total}; hcLaunchKernel((const void *)fill_f32, gb, tb, a, 0, 0); }
    { void *a[] = {&Bf, &total}; hcLaunchKernel((const void *)fill_f32, gb, tb, a, 0, 0); }
    { void *a[] = {&Ad, &total}; hcLaunchKernel((const void *)fill_f64, gb, tb, a, 0, 0); }
    { void *a[] = {&Bd, &total}; hcLaunchKernel((const void *)fill_f64, gb, tb, a, 0, 0); }
    hcDeviceSynchronize();

    double tf = 1e9, td = 1e9;
    for (int rep = 0; rep < 3; rep++) {
        double t0 = now_s();
        { void *a[] = {&Af, &Bf, &Cf, &n};
          hcLaunchKernel((const void *)gemm_f32, grid, block, a, 0, 0); }
        hcDeviceSynchronize();
        double dt = now_s() - t0;
        if (dt < tf) tf = dt;
    }
    for (int rep = 0; rep < 3; rep++) {
        double t0 = now_s();
        { void *a[] = {&Ad, &Bd, &Cd, &n};
          hcLaunchKernel((const void *)gemm_f64, grid, block, a, 0, 0); }
        hcDeviceSynchronize();
        double dt = now_s() - t0;
        if (dt < td) td = dt;
    }

    __half *Ah = NULL, *Bh = NULL;
    float  *Ch = NULL;
    hcMalloc((void **)&Ah, nn * sizeof(__half));
    hcMalloc((void **)&Bh, nn * sizeof(__half));
    hcMalloc((void **)&Ch, nn * sizeof(float));
    if (Ah && Bh) {
        { void *a[] = {&Ah, &total}; hcLaunchKernel((const void *)fill_f16, gb, tb, a, 0, 0); }
        { void *a[] = {&Bh, &total}; hcLaunchKernel((const void *)fill_f16, gb, tb, a, 0, 0); }
        hcDeviceSynchronize();
    }
    double th = 1e9;
    for (int rep = 0; rep < 3; rep++) {
        double t0 = now_s();
        { void *a[] = {&Ah, &Bh, &Ch, &n};
          hcLaunchKernel((const void *)gemm_f16, grid, block, a, 0, 0); }
        hcDeviceSynchronize();
        double dt = now_s() - t0;
        if (dt < th) th = dt;
    }

    /* 自检：C[0][0] = sum_k A[0][k] * B[k][0]，只搬 2n 个数回主机 */
    double *ra = (double *)malloc(sizeof(double) * n);
    double *cb = (double *)malloc(sizeof(double) * n);
    hcMemcpy(ra, Ad, sizeof(double) * n, hcMemcpyDeviceToHost);          /* A 的前 n 个 = 第 0 行 */
    for (int k = 0; k < n; k++)
        hcMemcpy(cb + k, Bd + (long)k * n, sizeof(double), hcMemcpyDeviceToHost);
    double want = 0.0, got = 0.0;
    for (int k = 0; k < n; k++) want += ra[k] * cb[k];
    hcMemcpy(&got, Cd, sizeof(double), hcMemcpyDeviceToHost);

    printf("%6d %12.2f %12.2f %12.2f %8.3f %8.3f  %s\n", n,
           flops / td / 1e9, flops / tf / 1e9, flops / th / 1e9,
           (flops / tf) / (flops / td), (flops / th) / (flops / td),
           (fabs(got - want) <= 1e-2 * (fabs(want) + 1.0)) ? "ok" : "MISMATCH");
    free(ra); free(cb);

    hcFree(Af); hcFree(Bf); hcFree(Cf);
    hcFree(Ad); hcFree(Bd); hcFree(Cd);
}

static void bw_case(long n)
{
    float *af=NULL,*bf=NULL,*cf=NULL; double *ad=NULL,*bd=NULL,*cd=NULL;
    hcMalloc((void**)&af,n*4); hcMalloc((void**)&bf,n*4); hcMalloc((void**)&cf,n*4);
    hcMalloc((void**)&ad,n*8); hcMalloc((void**)&bd,n*8); hcMalloc((void**)&cd,n*8);
    int tb=256; int gb=(int)((n+tb-1)/tb);
    { void*a[]={&af,&n}; hcLaunchKernel((const void*)fill_f32,gb,tb,a,0,0); }
    { void*a[]={&bf,&n}; hcLaunchKernel((const void*)fill_f32,gb,tb,a,0,0); }
    { void*a[]={&ad,&n}; hcLaunchKernel((const void*)fill_f64,gb,tb,a,0,0); }
    { void*a[]={&bd,&n}; hcLaunchKernel((const void*)fill_f64,gb,tb,a,0,0); }
    hcDeviceSynchronize();
    double t32=1e9,t64=1e9;
    for(int r=0;r<3;r++){double t0=now_s();
        { void*a[]={&af,&bf,&cf,&n}; hcLaunchKernel((const void*)stream_f32,gb,tb,a,0,0); }
        hcDeviceSynchronize(); double d=now_s()-t0; if(d<t32)t32=d;}
    for(int r=0;r<3;r++){double t0=now_s();
        { void*a[]={&ad,&bd,&cd,&n}; hcLaunchKernel((const void*)stream_f64,gb,tb,a,0,0); }
        hcDeviceSynchronize(); double d=now_s()-t0; if(d<t64)t64=d;}
    printf("BW  n=%ld  FP32 %.1f GB/s   FP64 %.1f GB/s\n",
           n, 3.0*n*4/t32/1e9, 3.0*n*8/t64/1e9);
    hcFree(af);hcFree(bf);hcFree(cf);hcFree(ad);hcFree(bd);hcFree(cd);
}

int main(int argc, char **argv)
{
    int nmax = (argc > 1) ? atoi(argv[1]) : 4096;
    printf("# TILE=%d\n", TILE);
    printf("%6s %12s %12s %12s %8s %8s\n", "n", "TP64", "TP32", "TP16", "s32", "s16");
    for (long nb = 1L<<24; nb <= (1L<<26); nb <<= 1) bw_case(nb);
    for (int n = 512; n <= nmax; n *= 2) run_case(n);
    return 0;
}
