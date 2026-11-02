# Race7 · FP32/FP64 混合精度 × LU 分解加速

一份**可复现的研究底稿**：把"混合精度量化"从神经网络语境搬到直接法线性求解，
量出"低精度 LU 还能把结果做到 FP64 精度"的**可行域边界**，并据此给出
算法选型、硬件落点与后续研究切入点。

> 一句话：**FP32（或 11 位）做 `O(n³)` 的分解，FP64 做 `O(n²)` 的残差，
> 再用 GMRES 精化把误差拉回目标精度**——覆盖 `κ` 到 `1e14`，加速 1.2–7×。

## 30 秒读法

1. [结论摘要](docs/00-结论摘要.md) —— 一页纸，五条发现 + 三条规则 + 选型速查
2. [能力边界图](figures/fig1_envelope.svg) —— 每个配置能撑到多大的 `κ`
3. [误差断崖图](figures/fig2_cliff.svg) —— 越界后是"发散"而不是"变慢"

## 文档

| # | 文档 | 内容 |
|---|---|---|
| 00 | [结论摘要](docs/00-结论摘要.md) | 一页纸 |
| 01 | [问题重构](docs/01-问题重构.md) | 为什么不能照搬权重量化；四精度槽位 |
| 02 | [算法族谱](docs/02-算法族谱.md) | 九类算法 + 横向对比表 |
| 03 | [误差理论与可行域](docs/03-误差理论与可行域.md) | 三条边界、正则化机理、精度预算表 |
| 04 | [实验证据](docs/04-实验证据.md) | 方法、六组结果、七条结论、局限 |
| 05 | [候选应用算法](docs/05-候选应用算法.md) | 五个筛选标准 + 九个应用评分 + 负样本 |
| 06 | [加速器映射](docs/06-加速器映射.md) | 槽位→单元、面积模型、四条设计规则 |
| 07 | [研究路线](docs/07-研究路线.md) | 五个空白、三个课题、四周计划 |
| 08 | [参考文献](docs/08-参考文献.md) | 26 条，标注核对状态 |
| 09 | [论文：能推导出的结论](docs/09-论文结论与推导.md) | 5 条命题 + 二分性推导 + 骨架 + 缺口 |
| 10 | [四级消融实验清单](docs/10-四级消融实验清单.md) | A/B/C/D 四因子的完整设计与 12 条结论 |
| 11 | [端到端波形对比](docs/11-端到端波形对比.md) | **评委口径**：换求解器后 99/100 波形不变（中位 3.4 µV） |
| 12 | [提交合规自查](docs/12-提交合规自查.md) | ①目录 ②性能报告逐条对照 + 仍存风险 |

## 图

| 图 | 说明 |
|---|---|
| [图 1 能力边界](figures/fig1_envelope.svg) | 各配置可用 `κ` 上限（条形图） |
| [图 2 误差断崖](figures/fig2_cliff.svg) | 前向误差 vs `κ`，贴合 `κ·u₆₄` 直到越界 |
| [图 3 迭代步数](figures/fig3_iterations.svg) | 精化步数随 `log κ` 增长 |
| [图 4 正则化](figures/fig4_regularization.svg) | `‖M⁻¹‖` 随 `κ` 饱和 |
| [图 5 预条件偏差](figures/fig5_precond_dev.svg) | `‖AM⁻¹−I‖` 被封顶 |
| [图 6 加速比](figures/fig6_speedup.svg) | 端到端加速比 vs `n` |
| [图 7 压缩 vs 重算](figures/fig7_compress_vs_recompute.svg) | 同精度下两种因子构造的 `‖M⁻¹‖` |
| [图 8 预条件偏差](figures/fig8_dev_vs_kappa.svg) | 压缩随 `κ` 发散，重算被封顶 |
| [图 9 相图](figures/fig9_phase_n1024.svg) | `(κ,s)` 平面上的最优精度档 |
| [图 11 端到端波形](figures/fig11_wave_e2e.svg) | 100 网表的 MAE vs 1 mV 判据 + 最差用例的边沿尖峰 |

> `figures/*.png` 是无字体环境下的**版式预览**（文字渲染成色块，仅供检查排版），
> 正式图表是 `*.svg`，直接用浏览器打开即可。

## 复现

不需要 numpy / LAPACK / matplotlib（纯 Python 3.8+ 标准库）。

```bash
cd code
python3 run_experiments.py      # ~14 s，生成 results/scan.csv（759 行）
python3 diag_regularization.py  # ~1 s， 生成 results/reg.csv
python3 diag_compress.py        # ~2 s， 生成 results/reg2.csv（压缩 vs 重算）

# 电路矩阵上的实测（需在服务器上跑，见 code/omega_klu.c）
python3 make_figures.py         # 生成 figures/*.svg 与 results/summary.md
```

产物：

```
Race7/
├── paper/          草稿与排版：思路 / 提纲 / 实验记录 / main.tex / §3·§4·§6 完整版
├── docs/           00–09 共 10 篇
├── figures/        6 张 SVG（+ PNG 预览，由 code/preview_render.py 生成）
├── results/        scan.csv / reg.csv / reg2.csv / omega_circuit_btf.csv / summary.md
├── code/
│   ├── mplib.py               精度模拟器 + LU/IR/GMRES + 矩阵生成
│   ├── run_experiments.py     11 个变体 × 10 个 κ 的扫描
│   ├── diag_regularization.py ‖M⁻¹‖ / ‖AM⁻¹−I‖ 诊断
│   ├── diag_compress.py       压缩 vs 重算 对照
│   ├── omega_klu.c            电路矩阵 ρ 与 κ∞（C，链接 KLU；支持 BTF 与残差自检）
│   ├── lu_bench.c             FP32/FP64 LU 吞吐基准（测 s）
│   ├── phase_diagram.py       (κ,s) 相图与交叉点 n*
│   ├── glu_rho.c              task1_glu 的 [RHO] 钩子（含补丁）
│   ├── make_figures.py        出图与汇总表
│   ├── svgplot.py             极简 SVG 绘图（无依赖）
│   └── preview_render.py      SVG→PNG 预览（无依赖）
└── research_notes/            文献核查备忘与原始 PDF 文本
```

## 核心设计（三条规则）

- **R1 只降 `O(n³)` 的精度**：分解主循环是唯一值得加速的部分。
- **R2 残差必须是全精度，且它是唯一的 FP64 通路**（`O(n²)`，面积占比 `~12k/n`）。
- **R3 要低精度就重算，不要压缩**：压缩保留病态谱，会让 GMRES 精化失效。

## 状态

- [x] 精度模拟器（逐操作舍入，FMA 语义）
- [x] 11 个变体 × 10 个 `κ` × 5 seeds 扫描
- [x] 正则化机理诊断
- [x] 6 张图 + 自动汇总表
- [x] 文献核对（26 条，关键阈值与实测交叉验证）
- [ ] 分块内嵌精化（[07 篇](docs/07-研究路线.md) T2，下一步）
- [ ] 稀疏 LU 版本（自然序 → 列近似最小度）
- [ ] 真实 BLAS 对照（需要 numpy/scipy 环境）

## 边界

模拟器是**双精度中模拟**（`round_p(a*b+c)`），不含并行、通信、张量核的真实累加行为；
规模到 `n=576`（带状）与 `n=128`（稠密）。结论的定性部分稳，定量部分只作量级参考。
详见 [04 篇 4.10](docs/04-实验证据.md)。
