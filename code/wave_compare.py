#!/usr/bin/env python3
"""wave_compare.py -- 端到端波形对比，按赛题 S5 的**字面**判据给结果。

为什么不用残差：S5 判的是"仿真结果不变"（相关系数 > 0.9 且 MAE < 1 mV），
残差是求解器内部的量，评委不看。所以这里把两条路径的**瞬态波形**直接对拍。

两种口径，都报：

  1. 判据口径（评委）  :  r > 0.9  且  MAE < 1 mV
  2. 逐点口径（最强）  :  时间网格与全部信号值逐点完全相等 ⇒ "结果不变"

用法
----
    python3 wave_compare.py <参考目录> <待测目录> [--csv out.csv] [--quiet]

按文件名配对（*.out）。参考侧的点是插值目标，待测侧线性插值到参考点的时刻，
与官方 scripts/verify_waveform.py 的口径一致（解析器直接沿用其实现）。

退出码：0 = 全部通过；1 = 有失败/缺失。
"""

import argparse
import csv
import math
import os
import re
import sys
from collections import OrderedDict


# --------------------------------------------------------------------------
# 解析器：与官方 CUSPICE_public/scripts/verify_waveform.py 的
# parse_ngspice_output 保持一致（同口径才能和评委对上）。
# --------------------------------------------------------------------------
def parse_ngspice_output(filepath):
    """Parse an ngspice text output file, return OrderedDict signal -> [(t, v)]."""
    with open(filepath, "r") as f:
        text = f.read()

    all_sections = []
    pos = 0
    while True:
        m = re.search(r"^Index\s+time\s+(.+?)$", text[pos:], re.MULTILINE)
        if not m:
            break
        header_end = pos + m.end()
        signal_names = m.group(1).strip().split()
        sep_match = re.search(r"^-{5,}$", text[header_end:], re.MULTILINE)
        if not sep_match:
            pos = header_end
            continue
        sep_end = header_end + sep_match.end()

        data_start = sep_end + 1
        next_header = re.search(r"^Index\s+time\s+", text[data_start:], re.MULTILINE)
        if next_header:
            data_end = data_start + next_header.start()
        else:
            data_end = len(text)

        ff_pos = text.find("\f", data_start, data_end)
        if ff_pos != -1:
            data_end = ff_pos

        rows = []
        for line in text[data_start:data_end].strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                candidate_idx = int(parts[0])
                if candidate_idx >= 0 and len(parts) >= len(signal_names) + 2:
                    time_val = float(parts[1])
                    vals = [float(v) for v in parts[2:2 + len(signal_names)]]
                elif len(parts) >= len(signal_names) + 1:
                    time_val = float(parts[0])
                    vals = [float(v) for v in parts[1:1 + len(signal_names)]]
                else:
                    continue
                rows.append((time_val, vals))
            except (ValueError, IndexError):
                continue

        if rows:
            all_sections.append((signal_names, rows))

        pos = data_end + 1 if data_end < len(text) else len(text)

    seen_signal_sets = {}
    for sig_names, rows in all_sections:
        key = tuple(sig_names)
        if key not in seen_signal_sets:
            seen_signal_sets[key] = []
        seen_signal_sets[key].extend(rows)

    signals_data = OrderedDict()
    for sig_names, all_rows in seen_signal_sets.items():
        all_rows.sort(key=lambda r: r[0])
        deduped = {}
        for t, vals in all_rows:
            deduped[t] = vals
        sorted_times = sorted(deduped.keys())
        for i, name in enumerate(sig_names):
            signals_data[name] = [(t, deduped[t][i]) for t in sorted_times]

    return signals_data


def interp(pts, t):
    """线性插值，端点外夹住（与 check_waveform.py 一致）。"""
    if not pts:
        return 0.0
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    lo, hi = 0, len(pts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pts[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, v0 = pts[lo]
    t1, v1 = pts[hi]
    if t1 == t0:
        return v0
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def stats(ref, test):
    """返回 (MAE, 最大绝对误差, Pearson r, 点数)，按信号取最差的那个。

    MAE 单位与被测量一致（这里网表输出是 V，乘 1000 得 mV）。
    """
    worst = (0.0, 0.0, 1.0, 0)
    for name, gpts in ref.items():
        if name not in test:
            continue
        tpts = test[name]
        if len(gpts) < 3:
            continue
        xs = [v for _, v in gpts]
        ys = [interp(tpts, t) for t, _ in gpts]
        n = len(xs)
        mae = sum(abs(a - b) for a, b in zip(xs, ys)) / n
        mx = max(abs(a - b) for a, b in zip(xs, ys))
        mx_x = sum(xs) / n
        mx_y = sum(ys) / n
        sxy = sum((a - mx_x) * (b - mx_y) for a, b in zip(xs, ys))
        sxx = sum((a - mx_x) ** 2 for a in xs)
        syy = sum((b - mx_y) ** 2 for b in ys)
        r = sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 1.0
        if mae > worst[0]:
            worst = (mae, mx, r, n)
    return worst


def identical(a, b):
    """逐点完全一致（时间网格 + 所有信号值），即"结果不变"的最强口径。"""
    if list(a.keys()) != list(b.keys()):
        return False
    for name in a:
        if a[name] != b[name]:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir")
    ap.add_argument("test_dir")
    ap.add_argument("--csv")
    ap.add_argument("--mae-mv", type=float, default=1.0,
                    help="S5 的 MAE 阈值，单位 mV（默认 1.0）")
    ap.add_argument("--min-r", type=float, default=0.9, help="S5 的相关系数阈值")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    names = sorted(f for f in os.listdir(args.ref_dir) if f.endswith(".out"))
    if not names:
        print("参考目录里没有 *.out：%s" % args.ref_dir, file=sys.stderr)
        return 2

    rows = []
    npass = nfail = nmiss = nident = 0
    for fn in names:
        tp = os.path.join(args.test_dir, fn)
        case = fn[:-4]
        if not os.path.exists(tp):
            rows.append((case, "", "", "", "", "MISSING", ""))
            nmiss += 1
            continue
        try:
            ref = parse_ngspice_output(os.path.join(args.ref_dir, fn))
            tst = parse_ngspice_output(tp)
        except Exception as e:                                  # noqa: BLE001
            rows.append((case, "", "", "", "", "PARSE_ERR", str(e)[:40]))
            nfail += 1
            continue
        if not ref or not tst:
            rows.append((case, "", "", "", "", "EMPTY", ""))
            nfail += 1
            continue
        mae, mx, r, n = stats(ref, tst)
        ident = identical(ref, tst)
        ok = (mae * 1000.0 < args.mae_mv) and (r > args.min_r)
        npass += ok
        nfail += (not ok)
        nident += ident
        rows.append((case, "%.6f" % (mae * 1000.0), "%.6f" % (mx * 1000.0),
                     "%.9f" % r, n, "PASS" if ok else "FAIL",
                     "IDENTICAL" if ident else "DIFFERS"))

    if not args.quiet:
        print("%-22s %10s %10s %13s %6s %7s %s"
              % ("case", "MAE(mV)", "maxabs(mV)", "r", "npts", "S5", "逐点"))
        for r in rows:
            print("%-22s %10s %10s %13s %6s %7s %s" % r)

    worst = None
    for r in rows:
        if r[1] and (worst is None or float(r[1]) > float(worst[1])):
            worst = r
    print("\n参考 = %s\n待测 = %s" % (args.ref_dir, args.test_dir))
    print("S5 判据 (r>%g 且 MAE<%g mV):  PASS=%d  FAIL=%d  MISSING=%d"
          % (args.min_r, args.mae_mv, npass, nfail, nmiss))
    print("逐点完全一致: %d / %d" % (nident, len(rows)))
    if worst:
        print("最差用例: %s  MAE=%s mV  r=%s" % (worst[0], worst[1], worst[3]))

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["case", "MAE_mV", "maxabs_mV", "r", "npts", "S5", "pointwise"])
            w.writerows(rows)
        print("CSV -> %s" % args.csv)

    return 0 if (nfail == 0 and nmiss == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
