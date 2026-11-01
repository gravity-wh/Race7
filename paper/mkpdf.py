#!/usr/bin/env python3
"""mkpdf.py -- 无依赖的极简排版器：结构化块 -> PostScript -> PDF

为什么不用 LaTeX：运行环境里没有 TeX，也没有 groff 的 -ms 宏包。
这里直接用 PostScript 的 base-14 字体（Times-Roman / Times-Bold / Courier /
Symbol）排一版**文字稿**，再交给 ps2pdf。

用法：python3 mkpdf.py paper.txt out.pdf
输入：每行一个块，前缀决定类型
    T| 标题        S| 副标题      H| 一级标题    h| 二级标题
    P| 正文段落    Q| 摘要        B| 引用块       C| 代码/等宽
    F| 图注        L| 列表项      -| 分隔
"""
import re
import subprocess
import sys

# Times-Roman AFM 宽度（/1000 em），只收 ASCII
W = {32: 250, 33: 333, 34: 408, 35: 500, 36: 500, 37: 833, 38: 778, 39: 180,
     40: 333, 41: 333, 42: 500, 43: 564, 44: 250, 45: 333, 46: 250, 47: 278,
     58: 278, 59: 278, 60: 564, 61: 564, 62: 564, 63: 444, 64: 921, 91: 333,
     92: 278, 93: 333, 94: 469, 95: 500, 96: 333, 123: 480, 124: 200, 125: 480,
     126: 541}
for d in "0123456789":
    W[ord(d)] = 500
UP = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
              [722, 667, 667, 722, 611, 556, 722, 722, 333, 389, 722, 611, 889,
               722, 722, 556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611]))
LW = dict(zip("abcdefghijklmnopqrstuvwxyz",
              [444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500, 278, 778,
               500, 500, 500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444]))
W.update({ord(k): v for k, v in UP.items()})
W.update({ord(k): v for k, v in LW.items()})

GREEK = {"α": 0x61, "β": 0x62, "γ": 0x67, "δ": 0x64, "ε": 0x65, "ζ": 0x7A,
         "η": 0x68, "θ": 0x71, "ι": 0x69, "κ": 0x6B, "λ": 0x6C, "μ": 0x6D,
         "ν": 0x6E, "ξ": 0x78, "π": 0x70, "ρ": 0x72, "σ": 0x73, "τ": 0x74,
         "υ": 0x75, "φ": 0x66, "χ": 0x63, "ψ": 0x79, "ω": 0x77,
         "Γ": 0x47, "Δ": 0x44, "Θ": 0x51, "Λ": 0x4C, "Ξ": 0x58, "Π": 0x50,
         "Σ": 0x53, "Φ": 0x46, "Ψ": 0x59, "Ω": 0x57,
         "≤": 0xA3, "≥": 0xB3, "≈": 0xBB, "×": 0xB4, "·": 0xD7, "→": 0xAE,
         "∞": 0xA5, "≠": 0xB9, "±": 0xB1, "‖": 0xFA, "⁻": 0x2D}
FALLBACK = {"−": "-", "–": "-", "—": "--", "×": "x", "∈": " in ", "≤": "<=",
            "≥": ">=", "≈": "~", "≠": "!=", "·": ".", "→": "->", "∞": "inf",
            "‖": "||", "∀": "for all", "⇒": "=>", "∂": "d", "√": "sqrt",
            "∝": "~", "′": "'", "″": "''", "…": "...", "“": '"', "”": '"',
            "‘": "'", "’": "'", "•": "*", "λ": "lambda", "µ": "u"}

SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6",
       "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-"}

PAGE_W, PAGE_H = 595, 842          # A4 pt
ML, MR, MT, MB = 62, 62, 64, 56
TEXT_W = PAGE_W - ML - MR


def runs(text):
    """把文本切成 (font, string) 段：TR=Times, TI=Italic, SY=Symbol"""
    out, buf, cur = [], "", "TR"
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in SUP:
            if buf:
                out.append((cur, buf)); buf = ""
            j = i
            s = ""
            while j < len(text) and text[j] in SUP:
                s += SUP[text[j]]; j += 1
            out.append(("SU", s))
            i = j
            continue
        if ch in FALLBACK:
            ch2 = FALLBACK[ch]
            if buf:
                out.append((cur, buf)); buf = ""
            out.append(("TR", ch2))
            cur = "TR"
            i += 1
            continue
        if ord(ch) > 127 and ch not in GREEK:
            i += 1
            continue
        f = "SY" if ch in GREEK else "TR"
        if ch == "‖":
            f = "TR"; ch = "||"
        if f != cur and buf:
            out.append((cur, buf)); buf = ""
            cur = f
        if ch in GREEK and buf and cur == "SY":
            pass
        if ch in GREEK:
            buf += chr(GREEK[ch])
        else:
            buf += ch
        i += 1
    if buf:
        out.append((cur, buf))
    return out


def w_of(rs, size):
    tot = 0.0
    for f, s in rs:
        if f == "SU":
            tot += 0.6 * 0.6 * len(s) * size
        elif f == "SY":
            tot += 0.55 * len(s) * size
        else:
            tot += sum(W.get(ord(c), 500) for c in s) / 1000.0 * size
    return tot


def wrap(text, size, width, first_indent=0.0):
    words, lines, cur = text.split(), [], ""
    lim = width - first_indent
    for w in words:
        cand = (cur + " " + w).strip()
        if w_of(runs(cand), size) <= lim:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur, lim = w, width
    if cur:
        lines.append(cur)
    return lines


def esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class PS:
    def __init__(self):
        self.out = ["%!PS-Adobe-3.0", "%%Pages: (atend)", "%%BoundingBox: 0 0 %d %d"
                    % (PAGE_W, PAGE_H), "/SY /Symbol findfont def", "/TB /Times-Bold findfont def",
                    "/TI /Times-Italic findfont def", "/TR /Times-Roman findfont def",
                    "/CO /Courier findfont def"]
        self.y = PAGE_H - MT
        self.page = 1
        self.pages = 0
        self._newpage(first=True)

    def _newpage(self, first=False):
        if not first:
            self.out.append("showpage")
            self.pages += 1
        self.y = PAGE_H - MT

    def space(self, h):
        self.y -= h
        if self.y < MB + 20:
            self._newpage()

    def text(self, x, size, rs, font=None):
        for f, s in rs:
            fnt = font or f
            if fnt == "SU":
                self.out.append("TR %.1f scalefont setfont" % (size * 0.7))
                self.out.append("%.1f %.1f moveto (%s) show" % (x, self.y + size * 0.25, esc(s)))
                x += w_of([("SU", s)], size)
                continue
            self.out.append("%s %.1f scalefont setfont" % (fnt, size))
            self.out.append("%.1f %.1f moveto (%s) show" % (x, self.y, esc(s)))
            x += w_of([(f, s)], size)

    def para(self, text, size=9.8, lead=13.2, indent=0.0, font=None, gap=6.0):
        lines = wrap(text, size, TEXT_W, indent)
        for i, ln in enumerate(lines):
            self.space(lead)
            self.text(ML + (indent if i == 0 else 0), size, runs(ln), font)
        self.y -= gap

    def rule(self, w=None, t=0.5):
        w = w or TEXT_W
        self.out.append("%.2f setlinewidth" % t)
        self.out.append("%.1f %.1f moveto %.1f %.1f lineto stroke"
                        % (ML, self.y, ML + w, self.y))

    def mono(self, text, size=7.6, lead=9.6):
        for ln in text.split("\n"):
            self.space(lead)
            self.text(ML + 4, size, [("CO", ln)], "CO")

    def save(self, path):
        self.out.append("showpage")
        self.pages += 1
        self.out.append("%%Pages: %d" % self.pages)
        self.out.append("%%EOF")
        open(path, "w").write("\n".join(self.out))


def build(src, out_ps, out_pdf):
    ps = PS()
    for raw in open(src, encoding="utf-8"):
        ln = raw.rstrip("\n")
        if not ln.strip():
            continue
        kind, _, body = ln.partition("|")
        body = body.strip()
        if kind == "T":
            ps.space(18)
            for l in wrap(body, 17, TEXT_W):
                ps.space(21); ps.text(ML, 17, runs(l), "TB")
            ps.space(6)
        elif kind == "S":
            for l in wrap(body, 10.5, TEXT_W):
                ps.space(14); ps.text(ML, 10.5, runs(l), "TI")
            ps.space(10); ps.rule()
        elif kind == "H":
            ps.space(16)
            ps.text(ML, 12.5, runs(body), "TB"); ps.space(5)
        elif kind == "h":
            ps.space(9)
            ps.text(ML, 10.5, runs(body), "TI"); ps.space(3)
        elif kind == "Q":
            ps.para(body, size=9.2, lead=12.4, indent=14, font="TI", gap=10)
        elif kind == "B":
            ps.para(body, size=9.2, lead=12.2, indent=14, font="TI", gap=8)
        elif kind == "F":
            ps.space(3)
            ps.text(ML, 8.4, runs(body), "TI"); ps.space(6)
        elif kind == "L":
            ps.space(12)
            ps.text(ML + 10, 9.8, runs("•")); ps.text(ML + 22, 9.8, runs(body))
            ps.space(2)
        elif kind == "C":
            ps.mono(body); ps.space(4)
        elif kind == "-":
            ps.space(4); ps.rule(t=0.3); ps.space(4)
        else:
            ps.para(body)
    ps.save(out_ps)
    subprocess.run(["ps2pdf", out_ps, out_pdf], check=True)
    return ps.pages


if __name__ == "__main__":
    n = build(sys.argv[1], sys.argv[2], sys.argv[3])
    print("pages:", n, "->", sys.argv[3])
