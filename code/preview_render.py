"""preview_render.py -- 把本项目生成的 SVG 子集渲染成 PNG，用于人工检查版式。

只支持 svgplot.py 实际用到的元素: rect / line / path(M,L) / circle / text。
文字用浅灰方块占位（只检查布局，不检查字形）。
"""
import re
import struct
import sys
import zlib
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"


def hex2rgb(s, default=(0, 0, 0)):
    if not s or s == "none":
        return default
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    return default


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.buf = bytearray(b"\xff" * (w * h * 3))

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (int(y) * self.w + int(x)) * 3
            self.buf[i:i + 3] = bytes(c)

    def rect(self, x, y, w, h, c, fill=True):
        x0, y0 = int(round(x)), int(round(y))
        x1, y1 = int(round(x + w)), int(round(y + h))
        if fill:
            for yy in range(max(0, y0), min(self.h, y1 + 1)):
                base = yy * self.w * 3
                for xx in range(max(0, x0), min(self.w, x1 + 1)):
                    i = base + xx * 3
                    self.buf[i:i + 3] = bytes(c)
        else:
            self.line(x0, y0, x1, y0, c, 1)
            self.line(x0, y1, x1, y1, c, 1)
            self.line(x0, y0, x0, y1, c, 1)
            self.line(x1, y0, x1, y1, c, 1)

    def line(self, x0, y0, x1, y1, c, w=1.0):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        r = max(0.5, w / 2.0)
        for k in range(n + 1):
            t = k / n
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            rr = int(r)
            for dy in range(-rr, rr + 1):
                for dx in range(-rr, rr + 1):
                    if dx * dx + dy * dy <= r * r + 0.3:
                        self.px(x + dx, y + dy, c)

    def circle(self, cx, cy, rad, c, fill=True, w=1.0):
        if fill:
            for yy in range(int(cy - rad), int(cy + rad) + 1):
                for xx in range(int(cx - rad), int(cx + rad) + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= rad * rad:
                        self.px(xx, yy, c)
        else:
            steps = max(16, int(rad * 6))
            prev = None
            for k in range(steps + 1):
                a = 2 * 3.141592653589793 * k / steps
                p = (cx + rad * __import__("math").cos(a), cy + rad * __import__("math").sin(a))
                if prev:
                    self.line(prev[0], prev[1], p[0], p[1], c, w)
                prev = p

    def png(self, path):
        raw = b"".join(b"\x00" + bytes(self.buf[y * self.w * 3:(y + 1) * self.w * 3])
                       for y in range(self.h))

        def chunk(t, d):
            return (struct.pack(">I", len(d)) + t + d +
                    struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
                    chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _collect_offsets(root):
    """把 <g transform="translate(dx,dy)"> 的位移累加到每个后代元素上。"""
    off = {}

    def walk(el, dx, dy):
        t = el.get("transform") or ""
        m = re.search(r"translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s*\)", t)
        if m:
            dx += float(m.group(1))
            dy += float(m.group(2))
        off[id(el)] = (dx, dy)
        for ch in el:
            walk(ch, dx, dy)

    walk(root, 0.0, 0.0)
    return off


def render(path, out, scale=1.0):
    tree = ET.parse(path).getroot()
    W = int(float(tree.get("width")) * scale)
    H = int(float(tree.get("height")) * scale)
    cv = Canvas(W, H)
    off = _collect_offsets(tree)
    for el in tree.iter():
        tag = el.tag.replace(NS, "")
        dx, dy = off.get(id(el), (0.0, 0.0))
        g = lambda k, d="0": float(el.get(k, d) or d)
        X = lambda k, d="0": float(el.get(k, d) or d) + dx
        Y = lambda k, d="0": float(el.get(k, d) or d) + dy
        stroke = hex2rgb(el.get("stroke"), (150, 150, 150))
        fill = el.get("fill")
        if tag == "rect":
            rw, rh = el.get("width", "0"), el.get("height", "0")
            if rw.endswith("%"):
                return_dim_w = float(rw[:-1]) / 100.0 * W
                w_ = return_dim_w
            else:
                w_ = float(rw)
            if rh.endswith("%"):
                h_ = float(rh[:-1]) / 100.0 * H
            else:
                h_ = float(rh)
            if fill and fill != "none":
                cv.rect(X("x") * scale, Y("y") * scale, w_ * scale,
                        h_ * scale, hex2rgb(fill))
            if el.get("stroke") and el.get("stroke") != "none":
                cv.rect(X("x") * scale, Y("y") * scale, w_ * scale,
                        h_ * scale, stroke, fill=False)
        elif tag == "line":
            cv.line(X("x1") * scale, Y("y1") * scale, X("x2") * scale, Y("y2") * scale,
                    stroke, max(1.0, g("stroke-width", "1") * scale))
        elif tag == "path":
            d = el.get("d", "")
            toks = re.findall(r'([ML])(-?[\d.]+),(-?[\d.]+)', d)
            prev = None
            for _, xs, ys in toks:
                p = ((float(xs) + dx) * scale, (float(ys) + dy) * scale)
                if prev:
                    cv.line(prev[0], prev[1], p[0], p[1], stroke,
                            max(1.0, g("stroke-width", "1") * scale))
                prev = p
        elif tag == "circle":
            cv.circle(X("cx") * scale, Y("cy") * scale, max(1.0, g("r") * scale),
                      stroke, fill=False, w=2.0)
        elif tag == "text":
            txt = (el.text or "")
            fs = g("font-size", "12") * scale
            anchor = el.get("text-anchor", "start")
            est = sum(fs * (1.0 if ord(c) > 127 else 0.56) for c in txt)
            x = X("x") * scale
            y = Y("y") * scale
            if anchor == "middle":
                x -= est / 2
            elif anchor == "end":
                x -= est
            if "rotate" in (el.get("transform") or "") or (el.get("transform") or ""):
                # 旋转文字（y 轴标题）用竖条占位
                cv.rect(x - fs, y - est / 2, fs, est, (215, 215, 215))
            else:
                cv.rect(x, y - fs * 0.8, est, fs * 0.95, (222, 222, 222))
    cv.png(out)
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        o = p.replace(".svg", ".png")
        render(p, o)
        print("rendered", o)
