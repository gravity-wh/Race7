"""svgplot.py -- 极简 SVG 折线图（不依赖 matplotlib），图例自动放到右侧并扩展画布"""
import math

FONT = "'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif"
COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
          "#0891b2", "#be185d", "#4d7c0f", "#475569", "#b45309"]


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _text_w(s, size=12):
    w = 0.0
    for ch in str(s):
        w += size * (1.0 if ord(ch) > 127 else 0.56)
    return w


def _nice_ticks(lo, hi, n=6):
    if hi <= lo:
        return [lo]
    span = hi - lo
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 2.5, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi * (1 + 1e-9):
        out.append(t)
        t += step
    return out


def _log_ticks(lo, hi):
    out = []
    for k in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1):
        v = 10.0 ** k
        if lo * 0.999 <= v <= hi * 1.001:
            out.append(v)
    return out


def _fmt_log(v):
    k = int(round(math.log10(v)))
    return "1" if k == 0 else ("1e%d" % k)


def _fmt_num(v):
    if v == 0:
        return "0"
    if abs(v) >= 1e4 or abs(v) < 0.01:
        return "%.0e" % v
    return "%g" % v


class Panel:
    def __init__(self, pw=620, ph=360, xlog=False, ylog=False, xlabel="",
                 ylabel="", title="", xlim=None, ylim=None, ml=80, mt=48, mb=62,
                 xticks=None, yticks=None):
        self.pw, self.ph = pw, ph
        self.xlog, self.ylog = xlog, ylog
        self.xlabel, self.ylabel, self.title = xlabel, ylabel, title
        self.xlim, self.ylim = xlim, ylim
        self.ml, self.mt, self.mb = ml, mt, mb
        self.xticks, self.yticks = xticks, yticks
        self.items = []

    def _tx(self, x):
        return math.log10(x) if self.xlog else x

    def _ty(self, y):
        return math.log10(y) if self.ylog else y

    def plot(self, xs, ys, label="", color=None, marker="o", dash=None, width=2.2):
        pts = []
        for x, y in zip(xs, ys):
            if x is None or y is None:
                continue
            if self.ylog and y <= 0:
                continue
            if self.xlog and x <= 0:
                continue
            pts.append((self._tx(x), self._ty(y)))
        self.items.append(dict(pts=pts, label=label, marker=marker, dash=dash,
                               color=color or COLORS[len(self.items) % len(COLORS)],
                               width=width))

    def hline(self, y, label="", color="#94a3b8", dash="6,4", width=1.4):
        self.items.append(dict(pts=[(0.0, self._ty(y))], label=label, color=color,
                               marker=None, dash=dash, width=width, hline=True))

    # ------------------------------------------------------------------
    def save(self, path):
        allp = [p for it in self.items if not it.get("hline") for p in it["pts"]]
        xs = [p[0] for p in allp]
        ys = [p[1] for p in allp]
        x0, x1 = (self._tx(self.xlim[0]), self._tx(self.xlim[1])) if self.xlim \
            else (min(xs), max(xs))
        y0, y1 = (self._ty(self.ylim[0]), self._ty(self.ylim[1])) if self.ylim \
            else (min(ys), max(ys))
        if x1 == x0:
            x1 = x0 + 1
        if y1 == y0:
            y1 = y0 + 1
        if self.xlog:
            x0, x1 = math.floor(x0), math.ceil(x1)
        if self.ylog:
            y0, y1 = math.floor(y0), math.ceil(y1)

        labels = [it["label"] for it in self.items if it["label"]]
        legend_w = max([_text_w(s) + 44 for s in labels] + [0]) + 10
        L = self.ml
        R = L + self.pw
        T = self.mt
        B = T + self.ph
        W = int(R + legend_w + 18)
        H = int(B + self.mb)

        def pxt(t):
            return L + (t - x0) / (x1 - x0) * (R - L)

        def pyt(t):
            return B - (t - y0) / (y1 - y0) * (B - T)

        o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d" font-family="%s">' % (W, H, W, H, _esc(FONT)),
             '<rect width="100%" height="100%" fill="#ffffff"/>']
        if self.title:
            o.append('<text x="%d" y="27" font-size="16" font-weight="600" fill="#0f172a">%s</text>'
                     % (L, _esc(self.title)))

        if self.xticks:
            xt = self.xticks
            xl = [_fmt_log(v) if math.log10(v) == int(math.log10(v)) and self.xlog
                  else _fmt_num(v) for v in xt]
        elif self.xlog:
            xt = _log_ticks(10 ** x0, 10 ** x1)
            xl = [_fmt_log(v) for v in xt]
        else:
            xt = _nice_ticks(x0, x1)
            xl = [_fmt_num(v) for v in xt]
        if self.yticks:
            yt = self.yticks
            yl = [_fmt_num(v) for v in yt]
        elif self.ylog:
            yt = _log_ticks(10 ** y0, 10 ** y1)
            yl = [_fmt_log(v) for v in yt]
        else:
            yt = _nice_ticks(y0, y1)
            yl = [_fmt_num(v) for v in yt]

        for v, s in zip(xt, xl):
            X = pxt(math.log10(v) if self.xlog else v)
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f7"/>' % (X, T, X, B))
            o.append('<text x="%.1f" y="%d" font-size="12" fill="#475569" text-anchor="middle">%s</text>'
                     % (X, B + 20, _esc(s)))
        for v, s in zip(yt, yl):
            Y = pyt(math.log10(v) if self.ylog else v)
            o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f7"/>' % (L, Y, R, Y))
            o.append('<text x="%d" y="%.1f" font-size="12" fill="#475569" text-anchor="end">%s</text>'
                     % (L - 8, Y + 4, _esc(s)))
        o.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#94a3b8"/>'
                 % (L, T, R - L, B - T))

        for it in self.items:
            if it.get("hline"):
                Y = pyt(it["pts"][0][1])
                o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" '
                         'stroke-width="%.1f" stroke-dasharray="%s"/>'
                         % (L, Y, R, Y, it["color"], it["width"], it["dash"]))
                continue
            if not it["pts"]:
                continue
            d = " ".join(("M" if i == 0 else "L") + "%.1f,%.1f" % (pxt(p[0]), pyt(p[1]))
                         for i, p in enumerate(it["pts"]))
            dash = (' stroke-dasharray="%s"' % it["dash"]) if it["dash"] else ""
            o.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.1f"%s '
                     'stroke-linejoin="round"/>' % (d, it["color"], it["width"], dash))
            for p in it["pts"]:
                o.append('<circle cx="%.1f" cy="%.1f" r="3.1" fill="#fff" stroke="%s" '
                         'stroke-width="1.8"/>' % (pxt(p[0]), pyt(p[1]), it["color"]))

        lx = R + 18
        ly = T + 6
        for it in self.items:
            if it.get("hline"):
                o.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="%s" '
                         'stroke-width="%.1f" stroke-dasharray="%s"/>'
                         % (lx, ly - 4, lx + 20, ly - 4, it["color"], it["width"], it["dash"]))
            else:
                o.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="%s" '
                         'stroke-width="%.1f"/>' % (lx, ly - 4, lx + 20, ly - 4, it["color"], it["width"]))
            if it["label"]:
                o.append('<text x="%d" y="%.0f" font-size="12" fill="#334155">%s</text>'
                         % (lx + 27, ly, _esc(it["label"])))
            ly += 21

        o.append('<text x="%.1f" y="%d" font-size="13" fill="#334155" text-anchor="middle">%s</text>'
                 % ((L + R) / 2, B + 46, _esc(self.xlabel)))
        o.append('<text x="20" y="%.1f" font-size="13" fill="#334155" text-anchor="middle" '
                 'transform="rotate(-90 20 %.1f)">%s</text>'
                 % ((T + B) / 2, (T + B) / 2, _esc(self.ylabel)))
        o.append("</svg>")
        with open(path, "w") as f:
            f.write("\n".join(o))
        return path


class HBar:
    """横向条形图：展示每个配置的能力边界（最大可用 κ）。"""

    def __init__(self, rows, title="", xlabel="", pw=560, rh=34, ml=250, mt=52, mb=64):
        # rows: [(label, log10_value, color, open_ended)]
        self.rows = rows
        self.title, self.xlabel = title, xlabel
        self.pw, self.rh, self.ml, self.mt, self.mb = pw, rh, ml, mt, mb

    def save(self, path):
        n = len(self.rows)
        lo = min(0, min(r[1] for r in self.rows))
        hi = max(r[1] for r in self.rows)
        hi = math.ceil(hi)
        lo = math.floor(lo) - 0.2
        L, R = self.ml, self.ml + self.pw
        T = self.mt
        B = T + n * self.rh + 12
        W = R + 150
        H = B + self.mb

        def px(t):
            return L + (t - lo) / (hi - lo) * (R - L)

        o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
             'font-family="%s">' % (W, H, W, H, _esc(FONT)),
             '<rect width="100%" height="100%" fill="#ffffff"/>']
        if self.title:
            o.append('<text x="%d" y="27" font-size="16" font-weight="600" fill="#0f172a">%s</text>'
                     % (L, _esc(self.title)))
        for k in range(int(lo) + 1, hi + 1):
            X = px(k)
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f7"/>' % (X, T, X, B))
            o.append('<text x="%.1f" y="%d" font-size="12" fill="#475569" text-anchor="middle">10^%d</text>'
                     % (X, B + 20, k))
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#94a3b8"/>' % (L, T, L, B))
        for i, (lab, val, color, open_end) in enumerate(self.rows):
            y = T + i * self.rh + 4
            h = self.rh - 12
            X = px(val)
            o.append('<rect x="%d" y="%d" width="%.1f" height="%d" fill="%s" opacity="0.88" rx="2"/>'
                     % (L, y, max(2.0, X - L), h, color))
            if open_end:
                o.append('<path d="M%.1f,%.1f l10,-6 l0,12 z" fill="%s"/>'
                         % (X + 2, y + h / 2, color))
            o.append('<text x="%d" y="%d" font-size="12" fill="#1e293b" text-anchor="end">%s</text>'
                     % (L - 10, y + h - 5, _esc(lab)))
            txt = ("≥ 1e%d" % int(val)) if open_end else ("1e%d" % int(val))
            o.append('<text x="%.1f" y="%d" font-size="11" fill="#475569">%s</text>'
                     % (X + (16 if open_end else 6), y + h - 5, txt))
        o.append('<text x="%.1f" y="%d" font-size="13" fill="#334155" text-anchor="middle">%s</text>'
                 % ((L + R) / 2, B + 46, _esc(self.xlabel)))
        o.append("</svg>")
        with open(path, "w") as f:
            f.write("\n".join(o))
        return path
