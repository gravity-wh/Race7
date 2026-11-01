# 实验结果索引

四因子消融（A/B/C/D）与论文证据的对应关系。全部数据可用仓库内脚本复跑。

## 端到端波形对比（评委口径）

100 个官方 single 网表，两条路径各跑一遍，按赛题 **S5 字面判据**（r>0.9 且 MAE<1 mV）对拍。
**换求解器不改变仿真结果**：中位偏差 3.4 µV，是判据的 1/300。

| 对比 | 变量 | 官方脚本口径（2% 相对） | **S5 口径（r>0.9, MAE<1 mV）** |
|---|---|---|---|
| golden vs CPU | 无（基线） | 96/100 | **100/100** |
| golden vs GPU | 基线 + 求解器 | 95/100 | **99/100** |
| CPU vs GPU | **仅求解器** | — | **99/100** |

- 唯一失败 test_017：单个开关沿错开一个时间步，MAE 2.19 mV（峰值 60.7 mV），r = 0.99993
- GPU 采用率 **94.96%**（120,742 次线性求解），与波形偏差**无关**（corr = 0.05）
- ⚠️ test_001 **非确定性**失败（5 次尝试 2 次成功，成功时 57 s vs 中位 5 s）
- ⚠️ 启动器已无回退：GPU 崩溃 = 该用例 0 张表 → S5 归零
- 详见 [11 篇](docs/11-端到端波形对比.md)，图 [fig11](figures/fig11_wave_e2e.svg)

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
| `results/wave/cmp_golden_cpu.csv` | 波形：官方 golden vs CPU 参考（逐用例 MAE/r） |
| `results/wave/cmp_golden_gpu.csv` | 波形：官方 golden vs GPU 加速路径 |
| `results/wave/cmp_cpu_gpu.csv` | 波形：CPU vs GPU（仅求解器） |
| `results/wave/gpu_adoption.tsv` | 逐用例 GPU 内解 / 回落 KLU 统计 |
| `results/wave/wave_*.csv` | 作图用的逐点波形与偏差 |

## 复跑

```bash
python3 code/run_experiments.py      # 稠密扫描 → results/scan.csv
python3 code/s11_threshold.py        # 门槛曲线 + fig10
python3 code/phase_diagram.py        # 相图
python3 code/make_figures.py         # 全部图

python3 code/wave_compare.py <ref_dir> <test_dir> --csv out.csv   # 波形对拍（S5 判据）
python3 code/fig_wave_e2e.py                                     # fig11
bash    code/run_wave_e2e.sh         # 服务器侧：100 网表 × 两路径全量重跑
```

服务器侧（x201）：
```bash
~/omega/omega <mtx> <btf> <scale> <eq> <tol>   # KLU + ρ + fill + 残差
~/lu_bench_gpu 4096                            # 吞吐 + 带宽
~/hcblas_bench 4096                            # 峰值
```

## 文档

- `docs/11-端到端波形对比.md` —— 波形对比（评委口径）、三路径、test_017 解剖、可靠性
- `docs/10-四级消融实验清单.md` —— 完整实验设计与 12 条结论
- `paper/07-论点重构与草稿修订.md` —— 论文叙事与修订方案
- `paper/03-section3.tex`、`04-section4.tex`、`05-section6.tex` —— 论文正文
