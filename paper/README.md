# paper/ —— 草稿与排版

```
paper/
├── 00-思路与草稿.md     ← 你的：研究轨迹、待定问题、草稿区
├── 01-提纲.md           ← 章节级提纲 + 图/表清单 + 写作顺序
├── 02-实验记录.md       ← 已完成的实验数据（写论文直接抄）
├── main.tex             ← LaTeX 骨架（\input 03-section3）
├── 03-section3.tex      ← §3 完整证明
├── 04-section4.tex      ← §4 完整证明
├── 05-section6.tex      ← §6 实验
├── figures/             ← 论文用图（SVG 源）
└── omega_circuit_btf.csv← 13 个电路矩阵的 ρ 数据
```

## 编译

`main.tex` 里 `\includegraphics` 指向 `.pdf`，需要先把 SVG 转成 PDF：

```bash
cd paper
for f in figures/*.svg; do rsvg-convert -f pdf -o "${f%.svg}.pdf" "$f"; done
pdflatex main && pdflatex main     # 两遍，交叉引用
```

没有 `rsvg-convert` 时可用 `inkscape --export-type=pdf` 或
`python3 -c "import cairosvg"`（本机都没有，需要在有 TeX 的环境里做）。

## 现在的状态

| 部分 | 状态 |
|---|---|
| 标题 / 摘要 | 初稿，可改 |
| §1 引言 | 钩子已写，贡献列表已列 |
| §2 记号 | 完成 |
| §3 主元地板 + 二分性 | **完整版**：`03-section3.tex`（引理 3.1/3.2、命题 3.3/3.4、定理 3.5、反例与适用范围） |
| §4 双侧界 | **完整版**：`04-section4.tex`（残差恒等式、收缩递推、前向界、两目标解耦） |
| §5 `(κ,s)` 相图 + Prop 3 | 图已出（3 个 n），公式完成 |
| §6 实验 | **完整版**：`05-section6.tex`（装置、相边界、机理、电路矩阵、双平台、效度威胁） |
| §7 应用 | 结论句已写，待补端到端数据 |
| §8 相关工作 | 待写 |

## 唯一硬缺口

平台 B 的 `s`。有了它，相图就从"参数化"变成"两条实测水平线"，Prop 3 才算被验证。
测量方法见 `02-实验记录.md` §4。

## 写作顺序

先 §3（最难）→ §5（图已就绪）→ §6（数字照抄 `02`）→ §1/§7/§8。
