"""Minimal SVG path parser/flattener (M,L,H,V,C,S,Q,T,Z; absolute + relative).

Used to rasterise the official Lian Li emblem path for the hub-cap and label textures.
"""
import re

_TOK = re.compile(r"[MmLlHhVvCcSsQqTtZzAa]|-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _cubic(p0, p1, p2, p3, n):
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
        out.append((x, y))
    return out


def _quad(p0, p1, p2, n):
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        out.append((mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
                    mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]))
    return out


def parse_path(d, curve_segments=24):
    """Return list of closed polylines (list of (x, y)) in SVG user units."""
    toks = _TOK.findall(d)
    i = 0
    subpaths = []
    cur = []
    x = y = 0.0
    sx = sy = 0.0
    last_ctrl = None
    cmd = None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if cur:
                    subpaths.append(cur)
                cur = []
                x, y = sx, sy
                last_ctrl = None
                continue
        # implicit repetition of previous command
        if cmd in "Mm":
            nx, ny = num(), num()
            if cmd == "m":
                nx += x
                ny += y
            if cur:
                subpaths.append(cur)
            cur = [(nx, ny)]
            x, y = nx, ny
            sx, sy = nx, ny
            cmd = "l" if cmd == "m" else "L"
            last_ctrl = None
        elif cmd in "Ll":
            nx, ny = num(), num()
            if cmd == "l":
                nx += x
                ny += y
            cur.append((nx, ny))
            x, y = nx, ny
            last_ctrl = None
        elif cmd in "Hh":
            nx = num()
            if cmd == "h":
                nx += x
            cur.append((nx, y))
            x = nx
            last_ctrl = None
        elif cmd in "Vv":
            ny = num()
            if cmd == "v":
                ny += y
            cur.append((x, ny))
            y = ny
            last_ctrl = None
        elif cmd in "Cc":
            c1 = [num(), num()]
            c2 = [num(), num()]
            p = [num(), num()]
            if cmd == "c":
                c1 = [c1[0] + x, c1[1] + y]
                c2 = [c2[0] + x, c2[1] + y]
                p = [p[0] + x, p[1] + y]
            cur.extend(_cubic((x, y), c1, c2, p, curve_segments))
            last_ctrl = c2
            x, y = p
        elif cmd in "Ss":
            c2 = [num(), num()]
            p = [num(), num()]
            if cmd == "s":
                c2 = [c2[0] + x, c2[1] + y]
                p = [p[0] + x, p[1] + y]
            if last_ctrl is not None:
                c1 = [2 * x - last_ctrl[0], 2 * y - last_ctrl[1]]
            else:
                c1 = [x, y]
            cur.extend(_cubic((x, y), c1, c2, p, curve_segments))
            last_ctrl = c2
            x, y = p
        elif cmd in "Qq":
            c1 = [num(), num()]
            p = [num(), num()]
            if cmd == "q":
                c1 = [c1[0] + x, c1[1] + y]
                p = [p[0] + x, p[1] + y]
            cur.extend(_quad((x, y), c1, p, curve_segments))
            last_ctrl = c1
            x, y = p
        else:
            raise ValueError("unsupported SVG path command %r" % cmd)
    if cur:
        subpaths.append(cur)
    return subpaths


def polygon_area(poly):
    a = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        a += x0 * y1 - x1 * y0
    return a / 2.0


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)
