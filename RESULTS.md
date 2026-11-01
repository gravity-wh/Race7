# 实验结果索引

四因子消融（A/B/C/D）与论文证据的对应关系。全部数据可用仓库内脚本复跑。

## 归因表（核心结论）

| 因子 | 倍率 | 证据 | 性质 |
|---|---|---|---|
| A 排序/填充 | ≤ 5.9×，中位数 1.0× | 12 矩阵 × 2 排序（`results/ablation_A.csv`） | 算法 |
| B 分块 | 1.5×（仅 FP32） | TILE 8/16/32 | 实现 |
| C 主元 | 1.0× | 6 矩阵 × 2 tolerance | 无 |
| D 核效率（残差） | 6.9× | 2.82 / 29.03 TFLOP/s | 实现 |
| **合计（典型）** | **≈10×** | | |
| **合计（最坏 rajat25）** | **≈61×** | | |

## 关键实测

| 量 | 值 | 来源 |
|---|---|---|
| hcBLAS SGEMM / DGEMM | 29.03 / 28.79 TFLOP/s | `code/hcblas_bench.cu` |
| 因此 s₃₂ | **1.008** | 同上 |
| 设备带宽 | 1.45 TB/s（FP64 stream） | `code/lu_bench_gpu.cu` |
| Ridge point | 20 FLOP/byte | P/B |
| 矩阵 AI | 10³–10⁴（算力受限） | fill 折算 |
| 我们的核效率 | 9.3% | 2.82/29.03 |
| 低精度档门槛 s₁₁* | 1.03–1.20 | `code/s11_threshold.py` |

## 数据文件

| 文件 | 内容 |
|---|---|
| `results/ablation_A.csv` | 12 矩阵 × {无 BTF, BTF} 的 fill |
| `results/omega_circuit_btf.csv` | 13 矩阵的 ρ、κ、残差、res/(ρu) |
| `results/scan.csv` | 稠密扫描：11 变体 × 10 κ × 5 seeds |
| `results/reg2.csv` | 压缩 vs 重算（二分性机理） |
| `results/s11_threshold.csv` | 门槛曲线 |
| `results/phase_diagram.csv` | 相图网格 |

## 复跑

```bash
python3 code/run_experiments.py      # 稠密扫描 → results/scan.csv
python3 code/s11_threshold.py        # 门槛曲线 + fig10
python3 code/phase_diagram.py        # 相图
python3 code/make_figures.py         # 全部图
```

服务器侧（x201）：
```bash
~/omega/omega <mtx> <btf> <scale> <eq> <tol>   # KLU + ρ + fill + 残差
~/lu_bench_gpu 4096                            # 吞吐 + 带宽
~/hcblas_bench 4096                            # 峰值
```

## 文档

- `docs/10-四级消融实验清单.md` —— 完整实验设计与 12 条结论
- `paper/07-论点重构与草稿修订.md` —— 论文叙事与修订方案
- `paper/03-section3.tex`、`04-section4.tex`、`05-section6.tex` —— 论文正文
