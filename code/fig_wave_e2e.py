#!/usr/bin/env python3
"""fig_wave_e2e.py -- 端到端波形对比图（CPU 参考 vs GPU 加速路径）。

输出 figures/fig11_wave_e2e.svg（两联图）：
  左：每个用例的 MAE（log 纵轴）+ 赛题 S5 的 1 mV 判据线
      → 98/99 个用例在判据线下方 1–3 个数量级，唯一例外浮在线上一格
  右：最差用例 test_017 的逐点 |Δ|（线性 mV）
      → 大偏差是开关沿上的稀疏尖峰，不是整体漂移

数据：results/wave/cmp_cpu_gpu.csv、results/wave/wave_<case>.csv
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import svgplot  # noqa: E402
from svgplot import Panel  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WAVE = os.path.join(ROOT, "results", "wave")


def load_cases():
    """返回 [(case_no, mae_mV), ...]，跳过无输出的用例。"""
    out = []
    with open(os.path.join(WAVE, "cmp_cpu_gpu.csv")) as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split(",")
            if len(parts) < 2 or not parts[1]:
                continue
            no = int(parts[0].split("_")[1])
            out.append((no, float(parts[1])))
    return sorted(out)


def load_wave(case):
    rows = []
    with open(os.path.join(WAVE, "wave_%s.csv" % case)) as f:
        next(f)
        for line in f:
            t, _ref, _test, d = line.strip().split(",")
            rows.append((float(t) * 1e6, abs(float(d))))
    return rows


def svg_size(path):
    s = open(path).read()
    m = re.search(r'width="(\d+)" height="(\d+)"', s)
    return int(m.group(1)), int(m.group(2)), s


def inner(s):
    i = s.index(">", s.index("<svg")) + 1
    j = s.rindex("</svg>")
    body = s[i:j]
    return re.sub(r'<rect width="100%" height="100%" fill="#ffffff"/>', "", body, count=1)


def main():
    cases = load_cases()
    npass = sum(1 for _, m in cases if m < 1.0)
    nfail = len(cases) - npass

    xs_ok = [c for c, m in cases if m < 1.0]
    ys_ok = [max(m, 1e-4) for _, m in cases if m < 1.0]
    xs_bad = [c for c, m in cases if m >= 1.0]
    ys_bad = [m for _, m in cases if m >= 1.0]

    p1 = Panel(pw=560, ph=300, xlog=False, ylog=True,
               xlabel="用例编号（test_0NN）", ylabel="MAE (mV)",
               title="端到端偏离：%d 通过 / %d 失败（红线 = 判据 1 mV）" % (npass, nfail),
               xlim=(0, 101), ylim=(1e-4, 1e2),
               yticks=[1e-4, 1e-3, 1e-2, 1e-1, 1e0, 1e1])
    p1.hline(1.0, label="S5 判据 1 mV", color="#dc2626")
    p1.plot(xs_ok, ys_ok, label="S5 通过", color="#059669")
    if xs_bad:
        p1.plot(xs_bad, ys_bad, label="S5 失败", color="#dc2626")

    wave = load_wave("test_017_tran")
    p2 = Panel(pw=560, ph=300,
               xlabel="时间 (µs)", ylabel="|Δv| (mV)",
               title="最差用例 test_017：偏差集中在开关沿（MAE 2.19 mV，峰值 60.7 mV）",
               ylim=(0, 65))
    p2.plot([t for t, _ in wave], [d for _, d in wave],
            label="|GPU − CPU|", color="#7c3aed", marker="o", width=1.4)
    p2.hline(1.0, label="S5 判据 1 mV", color="#dc2626")

    paths = []
    for i, p in enumerate((p1, p2)):
        tmp = os.path.join("/tmp", "wvpanel%d.svg" % i)
        p.save(tmp)
        paths.append(tmp)

    metas = [svg_size(p) for p in paths]
    W = metas[0][0] + metas[1][0]
    H = max(metas[0][1], metas[1][1])
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="%s">' % (W, H, W, H, svgplot.FONT),
           '<rect width="100%" height="100%" fill="#ffffff"/>']
    out.append('<g transform="translate(0,0)">%s</g>' % inner(metas[0][2]))
    out.append('<g transform="translate(%d,0)">%s</g>' % (metas[0][0], inner(metas[1][2])))
    out.append("</svg>")

    dst = os.path.join(ROOT, "figures", "fig11_wave_e2e.svg")
    with open(dst, "w") as f:
        f.write("\n".join(out))
    print("wrote %s (%dx%d)  cases=%d pass=%d fail=%d"
          % (dst, W, H, len(cases), npass, nfail))


if __name__ == "__main__":
    main()
