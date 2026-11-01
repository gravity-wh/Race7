/* glu_rho.c -- 分解后即时估算分量式增长因子 rho，并预测可达残差
 *
 *   rho = || diag(row_scale) |L||U| e ||_inf / ||A||_inf
 *   （分解的是 D^-1 A，故 A = D L U，误差界乘 D 而不是除）
 *
 * 理论依据:  |dA| <= u_f * diag(row_scale) |L||U|
 *            =>  可达相对残差 ~ rho * u_f
 * 所以打印 rho 就等于打印"这个矩阵能不能上低精度"。
 *
 * 只处理稠密存储（GLU_STORE_DENSE）：L 单位下三角 + U 上三角，列主序，
 * 行号 i 对应原矩阵的行 sym->perm[i]。
 */
#include "glu_internal.h"
#include <math.h>

void
glu_report_rho(const glu_factor *f, const glu_csr_d *A)
{
    int n, i, j;
    double normA = 0.0, rho = 0.0, pred32, pred64;
    double *urow, *s;

    if (!f || !A || !f->dense_lu || f->store != GLU_STORE_DENSE)
        return;
    n = f->n;
    if (n <= 0 || !A->rowptr || !A->values)
        return;

    urow = (double *)malloc((size_t)n * sizeof(double));
    s    = (double *)malloc((size_t)n * sizeof(double));
    if (!urow || !s) { free(urow); free(s); return; }

    /* ||A||_inf */
    for (i = 0; i < n; i++) {
        double rs = 0.0;
        int64_t k;
        for (k = A->rowptr[i]; k < A->rowptr[i + 1]; k++)
            rs += fabs(A->values[k]);
        if (rs > normA) normA = rs;
    }

    /* urow[j] = sum_{k>=j} |U_jk| */
    for (j = 0; j < n; j++) {
        double t = 0.0;
        for (i = j; i < n; i++)
            t += fabs(f->dense_lu[(int64_t)i + (int64_t)j * n]);
        urow[j] = t;
    }

    /* s[i] = sum_{j<=i} |L_ij| * urow[j]，L 对角为 1 */
    for (i = 0; i < n; i++) {
        double t = urow[i];
        for (j = 0; j < i; j++)
            t += fabs(f->dense_lu[(int64_t)i + (int64_t)j * n]) * urow[j];
        s[i] = t;
    }

    /* 还原行缩放与行排列 */
    for (i = 0; i < n; i++) {
        int r = f->sym ? f->sym->perm[i] : i;
        double sc = (f->row_scale && f->row_scale[r] != 0.0)
                    ? fabs(f->row_scale[r]) : 1.0;
        double v = s[i] * sc;   /* A = D * (D^-1 A) = D * L U */
        if (v > rho) rho = v;
    }
    if (normA > 0.0) rho /= normA;

    pred32 = rho * 5.96e-8;    /* u(FP32) = 2^-24 */
    pred64 = rho * 1.11e-16;   /* u(FP64) = 2^-53 */

    printf("[RHO] n=%d rho=%.4e pred_res_fp64=%.3e pred_res_fp32=%.3e fp32_ok=%s\n",
           n, rho, pred64, pred32, (pred32 <= 1e-6) ? "YES" : "NO");
    fflush(stdout);

    free(urow);
    free(s);
}
