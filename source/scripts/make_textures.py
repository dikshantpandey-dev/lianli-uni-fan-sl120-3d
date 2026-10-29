#!/usr/bin/env python3
"""Generate the PBR textures used by the Lian Li UNI FAN SL120 model.

Run with the system Python (needs numpy + Pillow):
    python3 make_textures.py <output_dir>

All textures are deterministic (fixed RNG seed) so the build is reproducible.
Normal maps use the OpenGL / glTF convention (+X right, +Y up, +Z out).

Dimensions used for the hub cap and the motor label are measured from the
official Lian Li product photos (see README "Sources").
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svgpath import parse_path  # noqa: E402

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "textures"))
FONT_DIR = os.environ.get("SL120_FONT_DIR", "/root/.cache/fonts/liberation-fonts-ttf-2.1.5")
EMBLEM_PATH = os.path.join(HERE, "..", "assets", "lianli_emblem_path.txt")
rng = np.random.default_rng(120)

# Emblem geometry in SVG units (measured from the official LIAN-LI-LOGO.svg path)
EMBLEM_CX, EMBLEM_CY, EMBLEM_R_OUT, EMBLEM_R_IN = 19.74, 20.0, 16.6, 14.72


# ----------------------------------------------------------------------------- helpers
def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def save(arr, name, mode="RGB"):
    arr = np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(arr, mode).save(os.path.join(OUT, name), optimize=True)
    print("wrote", name, arr.shape)


def periodic_noise(shape, sigma, rng_):
    """Tileable gaussian filtered noise (zero mean, unit std). sigma=(sy, sx) in px."""
    h, w = shape
    sy, sx = (sigma, sigma) if np.isscalar(sigma) else sigma
    n = rng_.standard_normal(shape)
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2.0 * (math.pi ** 2) * ((sx * fx) ** 2 + (sy * fy) ** 2))
    out = np.real(np.fft.ifft2(np.fft.fft2(n) * g))
    out -= out.mean()
    out /= out.std() + 1e-12
    return out


def normal_from_height(h, px_per_unit, periodic):
    """h in physical units (mm); returns RGB normal map (OpenGL convention)."""
    if periodic:
        dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
        drow = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    else:
        drow, dx = np.gradient(h)
    dx *= px_per_unit
    dv = -drow * px_per_unit  # image rows run downwards, +V runs upwards
    nx, ny, nz = -dx, -dv, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.dstack([nx / ln, ny / ln, nz / ln]) * 0.5 + 0.5


def emblem_polys():
    d = open(EMBLEM_PATH, encoding="utf-8").read()
    return parse_path(d, curve_segments=32)


def raster_polys(polys, size, to_px, supersample=1):
    """Even-odd fill of polygons -> float mask [0,1] (antialiased by supersampling)."""
    S = size * supersample
    acc = Image.new("1", (S, S), 0)
    for p in polys:
        m = Image.new("1", (S, S), 0)
        ImageDraw.Draw(m).polygon([tuple(v * supersample for v in to_px(x, y)) for x, y in p], fill=1)
        acc = ImageChops.logical_xor(acc, m)
    img = acc.convert("L")
    if supersample > 1:
        img = img.resize((size, size), Image.LANCZOS)
    return np.asarray(img).astype(np.float64) / 255.0


def blur(a, sigma_px):
    if sigma_px <= 0:
        return a
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2.0 * (math.pi ** 2) * (sigma_px ** 2) * (fx ** 2 + fy ** 2))
    pad = int(4 * sigma_px) + 2
    ap = np.pad(a, pad, mode="edge")
    fy = np.fft.fftfreq(ap.shape[0])[:, None]
    fx = np.fft.fftfreq(ap.shape[1])[None, :]
    g = np.exp(-2.0 * (math.pi ** 2) * (sigma_px ** 2) * (fx ** 2 + fy ** 2))
    out = np.real(np.fft.ifft2(np.fft.fft2(ap) * g))
    return out[pad:-pad, pad:-pad]


# ----------------------------------------------------------------------------- plastic
def make_plastic(n=1024, tile_mm=25.6):
    """Fine 'sand-blasted' texture of the PBT frame / blades (VDI-3400 like grain)."""
    px = n / tile_mm
    h = 0.62 * periodic_noise((n, n), 1.7, rng) + 0.38 * periodic_noise((n, n), 4.5, rng)
    h = np.tanh(0.85 * h)
    h *= 0.0035  # mm (peak ~3.5 micron) -> subtle grain
    save(normal_from_height(h, px, True), "T_PlasticGrain_N.png")
    rough = 0.90 + 0.10 * np.tanh(0.8 * periodic_noise((n, n), 3.0, rng))
    orm = np.dstack([np.ones((n, n)), rough, np.zeros((n, n))])
    save(orm, "T_PlasticGrain_ORM.png")


# ----------------------------------------------------------------------------- brushed alu
def make_brushed(w=1024, hgt=256, tile_mm=25.6):
    """Linear brushed / diamond-cut aluminium side plates (grain along U)."""
    px = w / tile_mm
    h = 0.7 * periodic_noise((hgt, w), (0.7, 90.0), rng) + 0.3 * periodic_noise((hgt, w), (2.5, 220.0), rng)
    h *= 0.0012
    save(normal_from_height(h, px, True), "T_AluBrushed_N.png")


# ----------------------------------------------------------------------------- hub cap
CAP_D = 26.0  # mm, spun-aluminium cap diameter (official front photo, scaled by the 105 mm hole pitch)


def make_hubcap(n=2048):
    px = n / CAP_D
    yy, xx = np.mgrid[0:n, 0:n]
    x = (xx + 0.5) / px - CAP_D / 2
    y = CAP_D / 2 - (yy + 0.5) / px
    r = np.hypot(x, y)

    # --- etched logo mask: two thin rings (emblem ring edges) + filled 'LI' glyph
    s = 8.6 / EMBLEM_R_OUT  # outer engraved ring radius 8.6 mm on the cap
    r_out, r_in = EMBLEM_R_OUT * s, EMBLEM_R_IN * s
    polys = emblem_polys()
    inner = polys[1]  # background region inside the ring (around the glyph)

    def to_px(X, Y):
        cx = (X - EMBLEM_CX) * s
        cy = -(Y - EMBLEM_CY) * s
        return ((cx + CAP_D / 2) * px, (CAP_D / 2 - cy) * px)

    inner_mask = raster_polys([inner], n, to_px, supersample=2)
    disc_in = np.clip((r_in - 0.08 - r) * px + 0.5, 0, 1)
    glyph = np.clip(disc_in - inner_mask, 0, 1)
    line_w = 0.20
    ring1 = np.clip((line_w / 2 - np.abs(r - r_out)) * px + 0.5, 0, 1)
    ring2 = np.clip((line_w / 2 - np.abs(r - r_in)) * px + 0.5, 0, 1)
    etch = np.clip(glyph + ring1 + ring2, 0, 1)
    etch_soft = blur(etch, 1.2)

    # --- turned (spun) finish: concentric micro grooves + slow radial waviness
    rr = np.linspace(0, CAP_D, 8192)
    wav = periodic_noise((1, 8192), (1.0, 60.0), rng)[0]
    h_turn = 0.0007 * np.sin(2 * math.pi * r / 0.085) + 0.0020 * np.interp(r, rr, wav)
    frost = 0.0015 * periodic_noise((n, n), 1.3, rng)
    h = h_turn * (1 - etch_soft) + (-0.018 + frost) * etch_soft
    nrm = normal_from_height(h, px, False)
    nimg = Image.fromarray(np.clip(nrm * 255 + 0.5, 0, 255).astype(np.uint8)).resize((n // 2, n // 2), Image.LANCZOS)
    nimg.save(os.path.join(OUT, "T_HubCap_N.png"), optimize=True)   # 1024 px is enough on screen
    print("wrote T_HubCap_N.png", nimg.size)

    alu = np.array([0.913, 0.922, 0.924])
    etched = np.array([0.80, 0.81, 0.82])
    base = alu[None, None, :] * (1 - etch_soft[..., None]) + etched[None, None, :] * etch_soft[..., None]
    save(lin_to_srgb(base), "T_HubCap_BaseColor.png")
    rough = 0.16 * (1 - etch_soft) + 0.48 * etch_soft
    orm = np.dstack([np.ones_like(r), rough, np.ones_like(r)])
    save(orm, "T_HubCap_ORM.png")

    # anisotropy direction texture (glTF KHR_materials_anisotropy): RG=direction, B=strength
    th = np.arctan2(y, x)
    dx, dy = -np.sin(th), np.cos(th)
    strength = 0.85 * (1 - etch_soft) * np.clip(r / 0.6, 0, 1)
    save(np.dstack([dx * 0.5 + 0.5, dy * 0.5 + 0.5, strength]), "T_HubCap_Anisotropy.png")


# ----------------------------------------------------------------------------- motor label
LABEL_D = 31.0  # mm texture frame; mapped onto the 30.4 mm label disc (photo scale correction 0.98)


def make_label(n=2048):
    """Back motor label. Layout measured from the official photo; the values printed on a
    real UNI FAN SL120 (DC 12 V 0.18 A / 800 ~ 1900 RPM / LED 5 V 0.65 A) come from a
    photo of retail SL120 fans (PC Gamer review)."""
    px = n / LABEL_D
    bg = (92, 93, 97)
    ink = (238, 238, 236)
    S = 2  # supersample for crisp vector shapes
    N = n * S
    img = Image.new("RGB", (N, N), bg)
    d = ImageDraw.Draw(img)

    def P(xm, ym):  # label mm (y up, origin centre) -> supersampled px
        return ((xm + LABEL_D / 2) * px * S, (LABEL_D / 2 - ym) * px * S)

    def mm(v):
        return v * px * S

    # emblem (full logo: thick ring + glyph), centre (0, 10.5), diameter 6.1 mm
    s = (6.1 / 2) / EMBLEM_R_OUT
    polys = emblem_polys()

    def to_px(X, Y):
        return P((X - EMBLEM_CX) * s, 10.5 - (Y - EMBLEM_CY) * s)

    m = Image.new("1", (N, N), 0)
    for p in polys:
        mm_ = Image.new("1", (N, N), 0)
        ImageDraw.Draw(mm_).polygon([to_px(X, Y) for X, Y in p], fill=1)
        m = ImageChops.logical_xor(m, mm_)
    img.paste(Image.new("RGB", (N, N), ink), (0, 0), m.convert("L"))

    # separator lines
    R = LABEL_D / 2
    for yl in (5.7, -5.72):
        half = math.sqrt(R * R - yl * yl) - 0.75
        d.rectangle([P(-half, yl + 0.17), P(half, yl - 0.17)], fill=ink)

    # text lines (Liberation Sans, metric compatible with Arial)
    reg = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")
    bold = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")

    def text_block(txt, font_path, cap_mm, cx, cy, width_mm=None, x_scale=None):
        probe = ImageFont.truetype(font_path, 400)
        hb = probe.getbbox("H")
        cap_ratio = (hb[3] - hb[1]) / 400.0
        size = int(round(mm(cap_mm) / cap_ratio))
        f = ImageFont.truetype(font_path, size)
        bb = f.getbbox(txt)
        tw, th_ = bb[2] - bb[0], bb[3] - bb[1]
        tile = Image.new("L", (tw + 8, th_ + 8), 0)
        ImageDraw.Draw(tile).text((4 - bb[0], 4 - bb[1]), txt, font=f, fill=255, stroke_width=3, stroke_fill=255)
        sx = (mm(width_mm) / tw) if width_mm else (x_scale or 1.0)
        tile = tile.resize((max(1, int(round(tile.width * sx))), tile.height), Image.LANCZOS)
        # vertical centre on cap height (digits/caps)
        hb2 = f.getbbox("H")
        cap_top = hb2[1] - bb[1] + 4
        cap_px = hb2[3] - hb2[1]
        X, Y = P(cx, cy)
        img.paste(Image.new("RGB", tile.size, ink), (int(X - tile.width / 2), int(Y - cap_top - cap_px / 2)), tile)
        return sx

    sx = text_block("LED 5 V, 0.65 A", reg, 2.16, 0.0, -3.28, width_mm=19.3)
    text_block("DC 12 V, 0.18 A", reg, 2.15, 0.0, 3.16, x_scale=sx)
    text_block("800 ~ 1900 RPM", reg, 2.20, 0.0, -0.03, x_scale=sx)
    text_block("RoHS", bold, 1.86, 6.34, -8.87, width_mm=5.6)

    # CE mark: two (slightly more than) semicircular letters, height 3.9 mm
    def ce_letter(cx, cy, Rr, w, with_bar):
        m = Image.new("L", (N, N), 0)
        dm = ImageDraw.Draw(m)
        dm.pieslice([P(cx - Rr, cy + Rr), P(cx + Rr, cy - Rr)], 80, 280, fill=255)
        rin = Rr - w
        dm.ellipse([P(cx - rin, cy + rin), P(cx + rin, cy - rin)], fill=0)
        if with_bar:
            dm.rectangle([P(cx - rin - 0.05, cy + w * 0.45), P(cx + 0.30, cy - w * 0.45)], fill=255)
        img.paste(Image.new("RGB", (N, N), ink), (0, 0), m)

    ce_letter(-6.65, -8.95, 1.95, 0.45, False)
    ce_letter(-4.05, -8.95, 1.95, 0.45, True)

    # WEEE crossed-out wheeled bin + bar (outline style)
    bx0, by0, bw, bh = -1.95, -10.36, 3.83, 3.44  # box (mm)

    def B(u, v):  # box-local (0..bw, 0..bh)
        return P(bx0 + u, by0 + v)

    lw = int(mm(0.2))
    body = [B(1.05, 2.62), B(2.78, 2.62), B(2.55, 0.62), B(1.28, 0.62)]
    d.line(body + [body[0]], fill=ink, width=lw, joint="curve")
    d.rectangle([B(0.92, 2.95), B(2.92, 2.74)], fill=ink)
    d.rectangle([B(1.65, 3.12), B(2.2, 2.95)], fill=ink)
    wr = 0.24
    cxw, cyw = 1.4, 0.40
    d.ellipse([B(cxw - wr, cyw + wr), B(cxw + wr, cyw - wr)], outline=ink, width=lw)
    xw = int(mm(0.3))
    d.line([B(0.12, 3.30), B(3.70, 0.14)], fill=ink, width=xw)
    d.line([B(0.12, 0.14), B(3.70, 3.30)], fill=ink, width=xw)
    d.rectangle([P(-1.9, -11.2), P(1.9, -12.1)], fill=ink)

    img = img.resize((n, n), Image.LANCZOS)
    img.save(os.path.join(OUT, "T_MotorLabel_BaseColor.png"), optimize=True)
    print("wrote T_MotorLabel_BaseColor.png", img.size)


# ----------------------------------------------------------------------------- RGB
def make_rgb(w=1024, h=8):
    """Addressable-RGB colour ramp (one full hue cycle along U)."""
    u = (np.arange(w) + 0.5) / w
    hue = u * 6.0
    i = np.floor(hue).astype(int) % 6
    f = hue - np.floor(hue)
    q, t = 1 - f, f
    rgb = np.zeros((w, 3))
    table = [(1, t, 0), (q, 1, 0), (0, 1, t), (0, q, 1), (t, 0, 1), (1, 0, q)]
    for k, (a, b, c) in enumerate(table):
        sel = i == k
        for ch, v in enumerate((a, b, c)):
            rgb[sel, ch] = v[sel] if isinstance(v, np.ndarray) else v
    # slight desaturation like real diffused LEDs, values are display (sRGB) colours
    rgb = 0.92 * rgb + 0.08
    save(np.repeat(rgb[None, :, :], h, axis=0), "T_RGB_Emissive.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_plastic()
    make_brushed()
    make_hubcap()
    make_label()
    make_rgb()
