# 混合精度 LU / 迭代精化：事实核查备忘（检索日 2026-10-29）

## 1. Carson & Higham (2018) 三精度 IR
- 设置 IR3：A、b、x 存于 u；LU 分解与三角回代于 u_f；残差于 u_r；更新于 u。
- 前向误差（Thm 3.2）：|x−x̂_{i+1}| ≤ F_i|x−x̂_i|+f_i，‖F_i‖∞ ≤ 2u_s·min{cond(A), κ∞(A)µ_i} + u_s‖E_i‖∞，其中 u_s 为"求解精度"。
- 收敛（Cor 3.3）：φ_i 为该界 ≪1 时，误差每步约缩 φ_i 倍，直到 ‖x−x̂‖∞/‖x‖∞ ≲ 4p·u_r·cond(A,x)+u。速率只依赖 u_s，极限精度只依赖 u 与 u_r。
- 标准 LU-IR3：u_s=u_f，u_f‖E_i‖∞ ≈ 3n·u_f·‖|A⁻¹||L̂||Û|‖∞ ≈ 3n u_f cond(A)（≤ f(n)ρ_n u_f κ∞(A)）⇒ 收敛条件 κ∞(A)u_f ≪ 1。
- 后向误差（Thm 4.1/Cor 4.2）：(c₁κ∞(A)+c₂)u_s ≪ 1 时残差降至 ≈ p·u(‖b‖∞+‖A‖∞‖x̂‖∞)，即工作精度后向稳定；u_r 再高对后向误差无益。
- 失效：κ∞(A) ≳ 1/u_f 时 φ≳1，标准 IR 停滞/发散——fp32 约 6×10⁷，fp16 约 2×10³，bf16 约 3×10²。Table 7.1：(single,single,double) 保证 κ≤10⁸，(half,single,double) 仅 κ≤10⁴。

## 2. GMRES-IR 的关键差别与最大条件数
- 差别：GMRES 在 u 下解 Ãd=Û⁻¹L̂⁻¹r，故 u_s=u；φ_i≈2u·κ∞(Ã)µ_i+u‖E_i‖∞，κ∞(Ã)≲(1+µ_f κ∞(A))²（Eq. 8.3）。LU 只当预条件子，其精度不影响可达精度；早期 µ_i≪1 使 min{} 起"额外杠杆"作用。
- 判据（Amestoy et al. 2024, 式 (2.6)/(2.7)）：前向 κ(A) ≪ u^{−1/2}u_f^{−1}；后向 κ(A) ≪ u^{−1/2}u_f^{−1/2}。
- 数量级：fp32 LU+fp64 GMRES-IR ⇒ 前向 2^50.5≈1.6×10¹⁵，后向 2^38.5≈4×10¹¹；CH2018 Table 8.1 对 (single,double,quad) 报 κ∞(A)≤10¹⁶（fp16 LU 为 10¹²）。故"可处理最大条件数"约 10¹⁵–10¹⁶（再受 cond(A,x)u_r≤1 约束）；fp16 LU 约 10¹²。
- 实验：CH2018 Fig 10.9（single/double/quad）在 κ∞(A)>1/u 时仍收敛，randsvd mode 2 全程仅 7 次 GMRES；mode 3 时迭代数可达 O(n)，收益被抵消。

## 3. Higham & Mary (2022) 框架
- 五精度参数：u（工作/存储/更新）、u_r（残差）、u_f（分解+回代）、u_g（GMRES）、u_p（预条件矩阵乘）；三精度为其特例。角色分工：u_s 决定收敛速率，u 与 u_r 决定极限精度。
- Thm 6.2：φ_i=2min{cond(A),κ∞(A)µ_i}u_s+ξ_i≪1 时误差按 φ_i 缩小，极限 ≲ u+4p·cond(A,x)u_r。
- Thm 7.2（LU-IR）：‖|A⁻¹||L̂||Û|‖u_f≪1 即可达上述界；Thm 7.4（GMRES-IR5）：κ(A)²u_f²(u_g+κ(A)u_p)≪1。
- 主要结论：低精度只值得用于 O(n³) 或带宽受限部分；fp16 分解仅在 κ≲1/u_f 时保证收敛（fp16 2000、bf16 300）；范围（上/下溢）与舍入同等重要；tensor core 的 fp32 累加把后向误差从 n·u16 降到 u16+n·u32。

## 4. Ozaki scheme
- 原始：Ozaki, Ogita, Oishi, Rump (2012)，把输入拆成多个低精度分量，使低精度 GEMM 精确重构乘积，无需 EFT。
- Ootomo & Yokota (2022)：FP16/TF32 tensor core 上达到 FP32 精度 DGEMM——A100 上 51 TFlop/s（受限指数）与 33 TFlop/s（全 FP32 范围），对 FP32 SIMT 峰值 19.5 TFlop/s 为 ≈2.6×/1.7×。
- 整数/CRT 版 Ozaki scheme II：GH200 上 FP64 模拟 56.6–80.2 TFlop/s，四精度较原方案 2.3×（RTX 4090 上 7.4–9.8 TFlop/s）。
- 扩展：ADP（Schwarz 2025）在 GB200 / RTX Pro 6000 上较原生 FP64 GEMM 快 2.3×/13.2×，开销<10%；FP8 tensor core 版（Mukunoki 2025）。

## 5. HPL-MxP（arXiv 2509.19618）
- 精度组合：输入/输出/校验 fp64；LU 分解 fp16（可更低）配 tensor core fp32 累加；残差与 GMRES 精化在 fp64，低精度 LU 作左预条件子；计量仍为 (2/3)n³/t，后向误差按 n·ε64 归一。
- 性能：Fugaku 上 1 EFlop/s vs HPL 0.4 EFlop/s（≈2.5×）；GPU 系统接近 10 EFlop/s；文中称一般硬件渐近约 2×。
- 数值结论：矩阵须能无主元稳定分解且对角按 ~√n 缩放，否则后向误差劣化 2–5 个数量级；GMRES 收敛是主要不确定性。

## 6. 2024–2026 相关新论文
1. Amestoy et al., *Five-Precision GMRES-based IR*, SIMAX 2024：五精度统一误差分析并给出精度组合"配方"。
2. Ren et al., 四精度（fp64/32/16/8）分块 Cholesky + 静态调度, 2024：MxP 下 3× 加速。
3. Scott & Tůma, 半精度不完全 Cholesky 的防中断策略, 2024：fp16 预条件子可替代 fp64。
4. Ge & Zhang, GADI-IR 三精度 + 参数预测, 2025：FP16 内迭代 + GPR 预测参数。
5. Kashi et al., HPG-MxP 在 exascale 机上, SC25：fp64/fp32 混合稀疏 GMRES 端到端 1.6×。
6. Kouya, Ozaki scheme II 多精度 LU, 2026：INT8/FP8/FP64 后端自适应选型，最高 2.84×。
（另：Carrica et al. 2026 分层递归精度 Cholesky，MXU 上 5.07×。）

## 7. 量化 / 误差反馈用于 LU 存储？
- 未检索到以"量化 + 误差反馈"直接作用于 LU 因子存储或低精度 LU 分解的论文（arXiv 全文/标题检索，截至 2026-10）。
- 最接近：(a) Higham–Pranesh–Zounon 2019 用 A=H+E，fp16 存 H、补偿项存 E，等价一次性误差反馈式存储；(b) MX 微缩放（block-scaled 量化）用于 Cholesky，按舍入+下溢误差选最小格式，MXFP16 提速 1.79×、省内存约 30%（TOMS 2026，DOI 尚未分配）；(c) EFCP 把 error feedback 用于压缩预条件子（深度学习优化器），非 LU；(d) 低精度 IC 防中断。
- 结论：该方向在 LU 上是空白；非 arXiv 文献/专利未核实。

## 参考文献
[1] CARSON E, HIGHAM N J. Accelerating the solution of linear systems by iterative refinement in three precisions[J]. SIAM J. Sci. Comput., 2018, 40(2): A817–A847. https://doi.org/10.1137/17M1140819 （预印本 https://eprints.maths.manchester.ac.uk/2562/1/three_prec.pdf）
[2] AMESTOY P, BUTTARI A, HIGHAM N J, L'EXCELLENT J-Y, MARY T, VIEUBLÉ B. Five-precision GMRES-based iterative refinement[J]. SIAM J. Matrix Anal. Appl., 2024, 45(1): 529–552. https://doi.org/10.1137/23M1549079 ；https://hal.science/hal-03190686v2
[3] HIGHAM N J, MARY T. Mixed precision algorithms in numerical linear algebra[J]. Acta Numerica, 2022, 31: 347–414. https://doi.org/10.1017/S0962492922000022 ；https://hal.science/hal-03537373v2
[4] OZAKI K, OGITA T, OISHI S, RUMP S M. Error-free transformations of matrix multiplication by using fast routines of matrix multiplication and its applications[J]. Numer. Algorithms, 2012, 59(1): 95–118. https://doi.org/10.1007/s11075-011-9478-1
[5] OOTOMO H, YOKOTA R. Recovering single precision accuracy from Tensor Cores while surpassing the FP32 theoretical peak performance[J]. IJHPCA, 2022, 36(4): 475–491. https://arxiv.org/abs/2203.03341
[6] OZAKI K. Ozaki scheme II: A GEMM-oriented emulation of floating-point matrix multiplication using an integer modular technique[J]. IJHPCA, 2026. https://arxiv.org/abs/2504.08009
[7] DONGARRA J, LUSZCZEK P. HPL-MxP benchmark: Mixed-precision algorithms, iterative refinement, and scalable data generation[J]. IJHPCA, 2025. https://arxiv.org/abs/2509.19618 ；https://doi.org/10.1177/10943420251382476
[8] SCHWARZ A. Guaranteed DGEMM accuracy while using reduced precision tensor cores through extensions of the Ozaki scheme[C]//SCA/HPCAsia 2026. https://arxiv.org/abs/2511.13778
[9] REN J, LTAIEF H, ABDULAH S, KEYES D E. Accelerating mixed-precision out-of-core Cholesky factorization with static task scheduling[R]. 2024. https://arxiv.org/abs/2410.09819
[10] SCOTT J, TŮMA M. Avoiding breakdown in incomplete factorizations in low precision arithmetic[R]. 2024. https://arxiv.org/abs/2401.17957
[11] GE J, ZHANG J. Three-precision iterative refinement with parameter regularization and prediction for solving large sparse linear systems[R]. 2025. https://arxiv.org/abs/2501.04229
[12] KASHI A, KOUKPAIZAN N, LU H, MATHESON M, ORAL S, et al. Scaling the memory wall using mixed-precision—HPG-MxP on an exascale machine[C]//SC25. 2025. https://arxiv.org/abs/2507.11512
[13] KOUYA T. Accelerating multiple-precision LU decomposition with Ozaki scheme II[R]. 2026. https://arxiv.org/abs/2609.29554
[14] ABDURAKHMANOV A, MARY T, LTAIEF H, KEYES D E, FAHMY S A. Error-controlled mixed-precision Cholesky factorization with MX microscaling formats[J]. ACM Trans. Math. Softw., 2026, 52(4). https://hal.science/hal-05641535v2 （DOI 待分配）
[15] HIGHAM N J, PRANESH S, ZOUNON M. Squeezing a matrix into half precision, with an application to solving linear systems[J]. SIAM J. Sci. Comput., 2019, 41(4): A2536–A2551. https://doi.org/10.1137/18M1229511
[16] MODORANU I-V, KALINOV A, KURTIC E, FRANTAR E, ALISTARH D. Error feedback can accurately compress preconditioners[R]. 2023. https://arxiv.org/abs/2306.06098
