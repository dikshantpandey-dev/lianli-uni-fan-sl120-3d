"""Procedural geometry for the Lian Li UNI FAN SL120 (model space, millimetres).

Model space:  X right, Y up, Z toward the viewer (front / intake face at +Z).
This is identical to glTF / three.js axes; the Blender builder converts to Z-up.
All dimensions are documented in README.md (sources: Lian Li spec sheet + drawings,
measurements from official product photos calibrated on the 105 mm hole pitch).
"""
import math

from mathutils import Vector
from mathutils.geometry import tessellate_polygon

# ------------------------------------------------------------------ key dimensions (mm)
HALF = 60.0            # 120 x 120 frame
Z_FACE = 12.0          # frame body faces (pads bring total depth to 25.0)
Z_PAD = 12.5
CORNER_CH = 2.4        # outer corner chamfer
HOLE_PITCH = 105.0     # official
HOLE_R = 2.25          # official dia 4.5
HOLE_C = HOLE_PITCH / 2
R_DUCT = 51.2          # opening edge measured at r=51.8 incl. fillet
R_TIP = 50.5
R_HUB = 16.2
R_CAP = 13.0
N_BLADES = 7
SIDE_X = 59.05         # side recess wall (aluminium plates / side diffusers sit on it)


class MeshData:
    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []
        self.uvs = []      # per face: list of (u,v) per corner, or None (box projection later)
        self.mats = []
        self.smooth = []

    def v(self, p):
        self.verts.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.verts) - 1

    def f(self, idx, mat=0, uv=None, smooth=True):
        self.faces.append(tuple(idx))
        self.mats.append(mat)
        self.uvs.append(uv)
        self.smooth.append(smooth)

    def extend(self, other, mat_offset=0):
        base = len(self.verts)
        self.verts.extend(other.verts)
        for fc, m, uv, sm in zip(other.faces, other.mats, other.uvs, other.smooth):
            self.faces.append(tuple(i + base for i in fc))
            self.mats.append(m + mat_offset)
            self.uvs.append(uv)
            self.smooth.append(sm)
        return self

    def transformed(self, fn, mirror=False, name=None):
        out = MeshData(name or self.name)
        out.verts = [tuple(fn(p)) for p in self.verts]
        for fc, m, uv, sm in zip(self.faces, self.mats, self.uvs, self.smooth):
            if mirror:
                fc = tuple(reversed(fc))
                uv = list(reversed(uv)) if uv else None
            out.faces.append(fc)
            out.mats.append(m)
            out.uvs.append(uv)
            out.smooth.append(sm)
        return out


# ------------------------------------------------------------------ 2D helpers
def area2(p):
    a = 0.0
    for i in range(len(p)):
        x0, y0 = p[i]
        x1, y1 = p[(i + 1) % len(p)]
        a += x0 * y1 - x1 * y0
    return a / 2


def ccw(p):
    return list(p) if area2(p) > 0 else list(reversed(p))


def cw(p):
    return list(p) if area2(p) < 0 else list(reversed(p))


def circle(cx, cy, r, n, a0=0.0):
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / n), cy + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]


def miters(loop):
    n = len(loop)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(loop[i - 1]), Vector(loop[i]), Vector(loop[(i + 1) % n])
        e0 = (p1 - p0).normalized()
        e1 = (p2 - p1).normalized()
        n0 = Vector((-e0.y, e0.x))
        n1 = Vector((-e1.y, e1.x))
        m = n0 + n1
        if m.length < 1e-9:
            m = n0
        m.normalize()
        out.append(m / max(m.dot(n0), 0.25))
    return out


def cap(md, rings, up, mat, uv=None):
    flat = [i for r in rings for i in r]
    tris = tessellate_polygon([[Vector((md.verts[i][0], md.verts[i][1], 0.0)) for i in r] for r in rings])
    for t in tris:
        a, b, c = (flat[k] for k in t)
        pa, pb, pc = (Vector(md.verts[k]) for k in (a, b, c))
        nz = (pb - pa).cross(pc - pa).z
        if (nz > 0) != up:
            b, c = c, b
        md.f((a, b, c), mat, smooth=False)


def extrude(md, loops, z0, z1, mat=0, segs=3, mat_ff=None, mat_cf=None, mat_cb=None, caps=(True, True)):
    """Prism from 2D loops (first = outer, rest = holes) with quarter-round (segs>1) or
    chamfer (segs=1) edges: loop dict keys pts, rb (back radius), rf (front radius)."""
    fr, br = [], []
    for k, L in enumerate(loops):
        pts = cw(L['pts']) if k > 0 else ccw(L['pts'])
        m = miters(pts)
        rb, rf = L.get('rb', 0.0), L.get('rf', 0.0)
        sb = L.get('segs', segs) if rb > 0 else 0
        sf = L.get('segs', segs) if rf > 0 else 0
        prof = []
        if rb > 0:
            for s in range(sb + 1):
                ph = s / sb * math.pi / 2
                prof.append((rb - rb * math.sin(ph), z0 + rb - rb * math.cos(ph), 'b'))
        else:
            prof.append((0.0, z0, 'w'))
        if rf > 0:
            for s in range(sf + 1):
                ph = s / sf * math.pi / 2
                prof.append((rf - rf * math.cos(ph), z1 - rf + rf * math.sin(ph), 'f'))
        else:
            prof.append((0.0, z1, 'w'))
        rings = []
        for d, z, _ in prof:
            rings.append([md.v((p[0] + d * mm.x, p[1] + d * mm.y, z)) for p, mm in zip(pts, m)])
        n = len(pts)
        for s, (a, b) in enumerate(zip(rings[:-1], rings[1:])):
            in_front_fillet = prof[s + 1][2] == 'f' and prof[s][2] == 'f'
            mt = mat_ff if (in_front_fillet and mat_ff is not None) else mat
            for i in range(n):
                j = (i + 1) % n
                md.f((a[i], a[j], b[j], b[i]), mt, smooth=L.get('smooth', True))
        br.append(rings[0])
        fr.append(rings[-1])
    if caps[1]:
        cap(md, fr, True, mat if mat_cf is None else mat_cf)
    if caps[0]:
        cap(md, br, False, mat if mat_cb is None else mat_cb)
    return md


def lathe(md, prof, n, mat=0, a0=0.0, smooth=True, uvfn=None):
    """Revolve (r, z) profile (counter-clockwise in r-z half plane => outward normals)."""
    rings = []
    for r, z in prof:
        if r < 1e-7:
            vi = md.v((0.0, 0.0, z))
            rings.append([vi] * n)
        else:
            rings.append([md.v((r * math.cos(a0 + 2 * math.pi * i / n), r * math.sin(a0 + 2 * math.pi * i / n), z)) for i in range(n)])
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            q = []
            for vi in (a[i], a[j], b[j], b[i]):
                if vi not in q:
                    q.append(vi)
            if len(q) >= 3:
                uv = [uvfn(md.verts[vi]) for vi in q] if uvfn else None
                md.f(tuple(q), mat, uv=uv, smooth=smooth)
    return md


def box(md, x0, x1, y0, y1, z0, z1, mat=0, ch=0.0):
    """Axis aligned box (prism in XY extruded along Z) with optional chamfer on all Z edges."""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return extrude(md, [{'pts': pts, 'rb': ch, 'rf': ch, 'segs': 1}], z0, z1, mat)


# ------------------------------------------------------------------ frame body
def frame_outline():
    h, c = HALF, CORNER_CH
    rs0, rs1 = 39.0, 40.0   # side recess (aluminium plate + side diffusers) ends
    return [
        (h - c, -h), (h, -h + c), (h, -rs1), (SIDE_X, -rs0), (SIDE_X, rs0), (h, rs1), (h, h - c),
        (h - c, h), (39.2, h), (39.2, h - 1.0), (34.3, h - 1.0), (34.3, h),   # top notch (front photo)
        (-h + c, h), (-h, h - c), (-h, rs1), (-SIDE_X, rs0), (-SIDE_X, -rs0), (-h, -rs1), (-h, -h + c),
    ]


def build_frame_body():
    md = MeshData('Housing_Frame')
    loops = [{'pts': frame_outline(), 'rb': 0.5, 'rf': 0.5, 'segs': 2}]
    loops.append({'pts': circle(0, 0, R_DUCT, 128), 'rb': 0.7, 'rf': 0.7, 'segs': 3})
    for sx in (-1, 1):
        for sy in (-1, 1):
            loops.append({'pts': circle(sx * HOLE_C, sy * HOLE_C, HOLE_R, 28), 'rb': 0.0, 'rf': 0.0})
    extrude(md, loops, -Z_FACE, Z_FACE, 0)
    # hole bosses visible through the rubber pads (front and back)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for s in (1, -1):
                b = MeshData('boss')
                lathe(b, [(3.1, -0.05), (3.1, 0.30), (2.95, 0.45), (HOLE_R + 0.15, 0.45), (HOLE_R, 0.30), (HOLE_R, -0.05)], 28, 0)
                md.extend(b.transformed(lambda p, sx=sx, sy=sy, s=s: (p[0] + sx * HOLE_C, p[1] + sy * HOLE_C, s * (Z_FACE + p[2])), mirror=(s < 0)))
    return md


# ------------------------------------------------------------------ diffuser strip outline (left side, model coords)
# Measured on the official front photo (hole-pitch calibrated): exposed top 2.9 mm wide,
# inner bevel 2.3 mm (vertical part) / 1.0 mm (45 deg part), ends 3 mm from the frame edge.
def strip_polylines():
    def P(cx, cy):  # corner coords (from top-left corner, cx inward, cy downward)
        return (-HALF + cx, HALF - cy)
    O = [P(20.1, 3.0), P(2.4, 20.7)]
    I = [P(24.2, 3.0), P(5.3, 21.9)]
    B = [P(25.6, 3.0), P(7.6, 21.0)]

    def full(top):
        a, b = top
        return [a, b, (b[0], -b[1]), (a[0], -a[1])]
    return full(O), full(I), full(B)


def offset_open(poly, d):
    """Offset an open polyline to its LEFT by d, keeping end points on the original end lines (y=const)."""
    out = []
    n = len(poly)
    for i in range(n):
        p = Vector(poly[i])
        if i == 0 or i == n - 1:
            e = (Vector(poly[1]) - Vector(poly[0])) if i == 0 else (Vector(poly[-1]) - Vector(poly[-2]))
            e.normalize()
            nl = Vector((-e.y, e.x))
            # move along the offset line until it hits y = p.y
            q = p + nl * d
            if abs(e.y) > 1e-9:
                t = (p.y - q.y) / e.y
                q = q + e * t
            out.append((q.x, q.y))
        else:
            e0 = (Vector(poly[i]) - Vector(poly[i - 1])).normalized()
            e1 = (Vector(poly[i + 1]) - Vector(poly[i])).normalized()
            n0, n1 = Vector((-e0.y, e0.x)), Vector((-e1.y, e1.x))
            m = (n0 + n1).normalized()
            q = p + m * (d / max(m.dot(n0), 0.25))
            out.append((q.x, q.y))
    return out


STRIP_Z_TOP = 12.40
STRIP_Z_BOT = 9.45
CHANNEL_Z_BOT = 9.40


def build_strip(u0, u1):
    """Left-front diffuser strip; u0/u1 = emissive U at the top / bottom ends."""
    O, I, B = strip_polylines()
    # path parameter along the centre line
    C = [((o[0] + i[0]) / 2, (o[1] + i[1]) / 2) for o, i in zip(O, I)]
    L = [0.0]
    for a, b in zip(C[:-1], C[1:]):
        L.append(L[-1] + math.dist(a, b))
    U = [u0 + (u1 - u0) * l / L[-1] for l in L]
    md = MeshData('strip')
    zt, zf, zb = STRIP_Z_TOP, Z_FACE, STRIP_Z_BOT
    Ot = [md.v((p[0], p[1], zt)) for p in O]
    It = [md.v((p[0], p[1], zt)) for p in I]
    Bf = [md.v((p[0], p[1], zf)) for p in B]
    Ob = [md.v((p[0], p[1], zb)) for p in O]
    Bb = [md.v((p[0], p[1], zb)) for p in B]
    for k in range(3):
        uv = lambda va, vb: [(U[k], va), (U[k + 1], va), (U[k + 1], vb), (U[k], vb)]
        md.f((Ot[k], Ot[k + 1], It[k + 1], It[k]), uv=uv(0.0, 0.62))      # exposed top
        md.f((It[k], It[k + 1], Bf[k + 1], Bf[k]), uv=uv(0.62, 1.0))      # inner bevel
        md.f((Ob[k], Ob[k + 1], Ot[k + 1], Ot[k]), uv=[(U[k], 0.0), (U[k + 1], 0.0), (U[k + 1], 0.0), (U[k], 0.0)])
        md.f((Bf[k], Bf[k + 1], Bb[k + 1], Bb[k]), uv=[(U[k], 1.0)] * 4)
    for k in (0, 3):
        ring = [Ot[k], It[k], Bf[k], Bb[k], Ob[k]]
        md.f(tuple(ring) if k == 0 else tuple(reversed(ring)), uv=[(U[k], 0.5)] * 5)
    bottom = Ob + list(reversed(Bb))
    # bottom face: tessellate in 2D
    tris = tessellate_polygon([[Vector((md.verts[i][0], md.verts[i][1], 0)) for i in bottom]])
    for t in tris:
        a, b, c = (bottom[q] for q in t)
        pa, pb, pc = (Vector(md.verts[q]) for q in (a, b, c))
        if (pb - pa).cross(pc - pa).z > 0:
            b, c = c, b
        md.f((a, b, c), uv=[(0.5, 0.5)] * 3, smooth=False)
    return md


def channel_cutter_outline():
    O, _, B = strip_polylines()
    Oo = offset_open(O, -0.35)   # O runs top->bottom on the left side; left normal points inward => negative = outward
    return Oo + list(reversed(B))


def fix_orientation(md, centre, inward_hint=False):
    """Flip faces whose normal points toward `centre` (works for convex-ish small parts)."""
    c = Vector(centre)
    for k, fc in enumerate(md.faces):
        ps = [Vector(md.verts[i]) for i in fc]
        nrm = Vector((0, 0, 0))
        for i in range(len(ps)):
            nrm += ps[i].cross(ps[(i + 1) % len(ps)])
        cen = sum(ps, Vector((0, 0, 0))) / len(ps)
        if nrm.length < 1e-12:
            continue
        if nrm.dot(cen - c) < 0:
            md.faces[k] = tuple(reversed(fc))
            if md.uvs[k]:
                md.uvs[k] = list(reversed(md.uvs[k]))


# ------------------------------------------------------------------ corner pad (rubber)
PAD_DIAG = 22.4
PAD_BEVEL = 20.0


def build_pad():
    """Top-left front pad, corner coords mapped to model coords."""
    def P(cx, cy, z):
        return (-HALF + cx, HALF - cy, z)
    md = MeshData('pad')
    zb, zt, zbev = Z_FACE - 0.6, Z_PAD, Z_FACE + 0.05
    c = CORNER_CH
    foot = [(0, c), (c, 0), (PAD_DIAG, 0), (0, PAD_DIAG)]
    topf = [(0, c), (c, 0), (PAD_BEVEL, 0), (0, PAD_BEVEL)]
    hole = circle(7.5, 7.5, 3.2, 28)
    # flat top with hole
    t_out = [md.v(P(x, y, zt)) for x, y in topf]
    t_hole = [md.v(P(x, y, zt)) for x, y in hole]
    cap(md, [t_out, t_hole], True, 0)
    b_out = [md.v(P(x, y, zb)) for x, y in foot]
    b_hole = [md.v(P(x, y, zb)) for x, y in hole]
    cap(md, [b_out, b_hole], False, 0)
    # hole wall
    n = len(hole)
    for i in range(n):
        j = (i + 1) % n
        md.f((t_hole[i], t_hole[j], b_hole[j], b_hole[i]))
    # bevel and sides
    C1 = md.v(P(PAD_DIAG, 0, zbev))
    D1 = md.v(P(0, PAD_DIAG, zbev))
    md.f((t_out[2], C1, D1, t_out[3]), smooth=False)           # diagonal bevel
    md.f((b_out[2], b_out[3], D1, C1), smooth=False)           # diagonal wall
    md.f((b_out[0], b_out[1], t_out[1], t_out[0]), smooth=False)   # corner chamfer wall
    md.f((b_out[1], b_out[2], C1, t_out[2], t_out[1]), smooth=False)  # top edge wall
    md.f((b_out[3], b_out[0], t_out[0], t_out[3], D1), smooth=False)  # left edge wall
    fix_pad_orientation(md)
    return md


def fix_pad_orientation(md):
    # hole wall faces must point toward the hole axis; other side faces away from the pad centroid
    hc = Vector((-HALF + 7.5, HALF - 7.5))
    cen = Vector((-HALF + 9.0, HALF - 9.0, (Z_FACE + Z_PAD) / 2))
    for k, fc in enumerate(md.faces):
        ps = [Vector(md.verts[i]) for i in fc]
        nrm = Vector((0, 0, 0))
        for i in range(len(ps)):
            nrm += ps[i].cross(ps[(i + 1) % len(ps)])
        fcen = sum(ps, Vector((0, 0, 0))) / len(ps)
        d2 = (Vector((fcen.x, fcen.y)) - hc).length
        if d2 < 3.3 and abs(nrm.z) < 0.2 * nrm.length:   # hole wall -> normal toward axis
            want = Vector((hc.x - fcen.x, hc.y - fcen.y, 0))
        else:
            want = fcen - cen
        if nrm.dot(want) < 0:
            md.faces[k] = tuple(reversed(fc))


# ------------------------------------------------------------------ side plates & side diffusers (right side; mirrored for left)
def side_part(shape_yz, mat_face, mat_edge, chamfer):
    """Extrude a (y,z) outline along +X from SIDE_X to HALF with a chamfer on the outer face."""
    md = MeshData('side')
    extrude(md, [{'pts': shape_yz, 'rb': 0.0, 'rf': chamfer, 'segs': 1}], 0.0, HALF - SIDE_X - 0.02,
            mat=mat_face, mat_ff=mat_edge)
    # local (a=y, b=z, c=x) -> model (x=SIDE_X+c, y=a, z=b)
    return md.transformed(lambda p: (SIDE_X + 0.02 + p[2], p[0], p[1]))


def plate_shape():
    return [(-38.4, 0.0), (-31.8, -6.6), (31.8, -6.6), (38.4, 0.0), (31.8, 6.6), (-31.8, 6.6)]


def band_shape(front=True):
    z0, z1 = 7.0, 11.85
    sh = [(-33.55, z0), (33.55, z0), (38.4, z1), (-38.4, z1)]
    return sh if front else [(y, -z) for y, z in sh]


# ------------------------------------------------------------------ struts, motor housing, wires
STRUT_Z0, STRUT_Z1 = -11.7, -8.7
STRUT_LINES = (
    # (angle deg of the + arm, point the centre line passes through)  -- from official back photo
    (65.6, (1.5, 0.0)),
    (155.6, (0.0, 2.5)),
)


def _line_r_param(p0, d, r):
    # |p0 + t d| = r, t>0
    b = p0.dot(d)
    c = p0.dot(p0) - r * r
    return -b + math.sqrt(max(b * b - c, 0.0))


def bar(md, a, b, prof, mat=0):
    d = (b - a).normalized()
    nl = Vector((-d.y, d.x))
    r0 = [md.v((a.x + w * nl.x, a.y + w * nl.y, z)) for w, z in prof]
    r1 = [md.v((b.x + w * nl.x, b.y + w * nl.y, z)) for w, z in prof]
    n = len(prof)
    for i in range(n):
        j = (i + 1) % n
        md.f((r0[i], r0[j], r1[j], r1[i]), mat)
    md.f(tuple(reversed(r0)), mat, smooth=False)
    md.f(tuple(r1), mat, smooth=False)


def rounded_rect_prof(w, z0, z1, r, segs=3):
    hw = w / 2
    pts = []
    corners = [(hw - r, z0 + r, -90), (hw - r, z1 - r, 0), (-hw + r, z1 - r, 90), (-hw + r, z0 + r, 180)]
    for cx, cz, a0 in corners:
        for s in range(segs + 1):
            a = math.radians(a0 + 90 * s / segs)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return pts


def channel_prof(w, z0, z1, wall, depth):
    """U-channel (open toward the back face z0) for the cable strut, CCW in (w, z)."""
    hw = w / 2
    zf = z0 + depth
    return [(-hw, z0 + 0.3), (-hw + 0.3, z0), (-hw + wall, z0), (-hw + wall, zf), (hw - wall, zf), (hw - wall, z0),
            (hw - 0.3, z0), (hw, z0 + 0.3), (hw, z1 - 0.4), (hw - 0.4, z1), (-hw + 0.4, z1), (-hw, z1 - 0.4)]


CABLE_W, STRUT_W = 7.0, 5.2


def build_struts():
    md = MeshData('struts')
    wires = MeshData('Motor_Wires')
    for ang, through in STRUT_LINES:
        p0 = Vector(through)
        for sgn in (1, -1):
            d = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)))) * sgn
            t0 = _line_r_param(p0, d, 15.0)
            t1 = _line_r_param(p0, d, 52.6)
            a, b = p0 + d * t0, p0 + d * t1
            cable = (ang == 65.6 and sgn == 1)
            if cable:
                prof = channel_prof(CABLE_W, STRUT_Z0, STRUT_Z1, 1.0, 1.9)
                bar(md, a, b, [(w, z) for w, z in prof][::-1] if area2(prof) < 0 else prof)
                # four PVC wires lying in the channel
                ta = _line_r_param(p0, d, 17.2)
                aw, bw = p0 + d * ta, p0 + d * _line_r_param(p0, d, 53.2)
                nl = Vector((-d.y, d.x))
                for k in range(4):
                    off = (k - 1.5) * 0.93
                    ring = [(off + 0.43 * math.cos(2 * math.pi * i / 10), STRUT_Z0 + 1.9 - 0.45 + 0.43 * math.sin(2 * math.pi * i / 10)) for i in range(10)]
                    bar(wires, aw, bw, ring)
            else:
                bar(md, a, b, rounded_rect_prof(STRUT_W, STRUT_Z0, STRUT_Z1, 0.6))
    return md, wires


R_MOTOR = 17.4
Z_MOTOR_BACK, Z_MOTOR_FRONT = -11.7, -8.1


def build_motor_housing():
    md = MeshData('Motor_Housing')
    lathe(md, [(0, Z_MOTOR_BACK), (R_MOTOR - 0.6, Z_MOTOR_BACK), (R_MOTOR - 0.18, Z_MOTOR_BACK + 0.18),
               (R_MOTOR, Z_MOTOR_BACK + 0.6), (R_MOTOR, Z_MOTOR_FRONT - 0.3), (R_MOTOR - 0.3, Z_MOTOR_FRONT),
               (3.6, Z_MOTOR_FRONT), (3.6, Z_MOTOR_FRONT + 6.0), (0, Z_MOTOR_FRONT + 6.0)], 96)
    return md


LABEL_R = 15.2


def build_label():
    md = MeshData('Motor_Label')
    n = 96
    z = Z_MOTOR_BACK - 0.03
    c = md.v((0, 0, z))
    ring = [md.v((LABEL_R * math.cos(2 * math.pi * i / n), LABEL_R * math.sin(2 * math.pi * i / n), z)) for i in range(n)]
    D = 2 * LABEL_R

    def uv(i):
        x, y, _ = md.verts[i]
        # label is read from the BACK: mirror X so the print is not reversed
        return (0.5 - x / D, 0.5 + y / D)
    for i in range(n):
        j = (i + 1) % n
        md.f((c, ring[j], ring[i]), uv=[uv(c), uv(ring[j]), uv(ring[i])], smooth=False)
    return md


# ------------------------------------------------------------------ rotor
Z_HUB_TOP, Z_HUB_BACK = 11.2, -7.5


def build_hub():
    md = MeshData('hub')
    r = R_HUB
    prof = [(0, Z_HUB_BACK + 0.6), (r - 0.5, Z_HUB_BACK), (r, Z_HUB_BACK + 0.4), (r, Z_HUB_TOP - 1.2)]
    for s in range(1, 5):
        a = math.radians(90 * s / 4)
        prof.append((r - 1.2 + 1.2 * math.cos(a), Z_HUB_TOP - 1.2 + 1.2 * math.sin(a)))
    prof += [(R_CAP + 0.35, Z_HUB_TOP), (R_CAP + 0.30, Z_HUB_TOP - 0.55), (R_CAP + 0.02, Z_HUB_TOP - 0.55),
             (R_CAP + 0.02, Z_HUB_TOP - 0.45), (0, Z_HUB_TOP - 0.45)]
    lathe(md, prof, 112)
    return md


def build_cap():
    md = MeshData('Rotor_HubCap')
    zt = Z_HUB_TOP - 0.08
    D = 2 * R_CAP

    def uvf(p):
        return (0.5 + p[0] / D, 0.5 + p[1] / D)
    prof = [(0, zt - 0.40), (R_CAP - 0.05, zt - 0.40), (R_CAP, zt - 0.32), (R_CAP, zt - 0.22), (R_CAP - 0.22, zt)]
    for k in range(1, 8):
        prof.append((R_CAP - 0.22 - k * (R_CAP - 0.22) / 8, zt))
    prof.append((0, zt))
    lathe(md, prof, 128, uvfn=uvf)
    return md


def blade_frame(r, phi):
    """Planform (angles in rad) and axial positions at radius r (mm). Measured from official photo."""
    th_te = math.radians(phi + 1.02 * (r - 19.6))
    th_le = math.radians(phi + 38.0 + 1.163 * (r - 19.6))
    t = (r - 16.0) / (R_TIP - 16.0)
    z_le = 10.0 - 1.0 * t
    z_te = -5.5 + 1.5 * t
    return th_le, th_te, z_le, z_te


def naca_t(s):
    return 5 * (0.2969 * math.sqrt(max(s, 0)) - 0.1260 * s - 0.3516 * s * s + 0.2843 * s ** 3 - 0.1036 * s ** 4)


def r_tip_of(s):
    r = R_TIP
    if s < 0.16:
        x = (0.16 - s) / 0.16
        r -= 2.6 * (1 - math.sqrt(max(1 - x * x, 0)))
    if s > 0.80:
        x = (s - 0.80) / 0.20
        r -= 3.6 * (1 - math.sqrt(max(1 - x * x, 0)))
    return r


def build_blade(phi, NR=16, NC=13):
    md = MeshData('blade')
    r_root = 15.4
    ss = [0.5 * (1 - math.cos(math.pi * j / NC)) for j in range(NC + 1)]
    rings = []
    ring_uv = []
    for i in range(NR + 1):
        t = i / NR
        t = 1 - (1 - t) ** 1.15
        ring = []
        uvr = []
        # lower (pressure) TE->LE, then upper (suction) LE->TE
        order = [(-1, j) for j in range(NC, 0, -1)] + [(0, 0)] + [(1, j) for j in range(1, NC + 1)]
        for side, j in order:
            s = ss[j]
            r = r_root + (r_tip_of(s) - r_root) * t
            th_le, th_te, z_le, z_te = blade_frame(r, phi)
            u_le, u_te = r * th_le, r * th_te
            a, b = u_te - u_le, z_te - z_le
            C = math.hypot(a, b)
            ns = (b / C, -a / C)          # suction side normal in (u, z)
            if ns[1] < 0:
                ns = (-ns[0], -ns[1])
            camber = 0.065 * C * 4 * s * (1 - s) * (1 - 0.25 * s)
            tmax = 2.2 + (1.05 - 2.2) * min(max((r - 16.0) / (R_TIP - 16.0), 0), 1) ** 0.7
            th = max(tmax * naca_t(s), 0.17 if s > 0.96 else 0.0)
            off = camber + side * th
            u = u_le + a * s + ns[0] * off
            z = z_le + b * s + ns[1] * off
            ang = u / r
            ring.append(md.v((r * math.cos(ang), r * math.sin(ang), z)))
            uvr.append(((side if side else 1) * s * C / 25.6 + 2.0, r / 25.6))
        rings.append(ring)
        ring_uv.append(uvr)
    m = len(rings[0])
    for i in range(NR):
        for k in range(m):
            k2 = (k + 1) % m
            md.f((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]),
                 uv=[ring_uv[i][k], ring_uv[i][k2], ring_uv[i + 1][k2], ring_uv[i + 1][k]])
    # tip and root caps: strip between lower/upper points
    for i, outward in ((NR, True), (0, False)):
        R = rings[i]
        U = ring_uv[i]
        lo = list(reversed(R[:NC]))    # j=1..NC lower
        up = R[NC + 1:]                # j=1..NC upper
        le = R[NC]
        lou = list(reversed(U[:NC]))
        upu = U[NC + 1:]
        faces = [((le, up[0], lo[0]), (U[NC], upu[0], lou[0]))]
        for j in range(NC - 1):
            faces.append(((lo[j], up[j], up[j + 1], lo[j + 1]), (lou[j], upu[j], upu[j + 1], lou[j + 1])))
        for fc, uv in faces:
            md.f(fc, uv=list(uv), smooth=False)
        # orientation fix by radial direction
        for k in range(len(md.faces) - len(faces), len(md.faces)):
            ps = [Vector(md.verts[q]) for q in md.faces[k]]
            nrm = Vector((0, 0, 0))
            for q in range(len(ps)):
                nrm += ps[q].cross(ps[(q + 1) % len(ps)])
            cen = sum(ps, Vector((0, 0, 0))) / len(ps)
            radial = Vector((cen.x, cen.y, 0)).normalized()
            if (nrm.dot(radial) > 0) != outward:
                md.faces[k] = tuple(reversed(md.faces[k]))
                md.uvs[k] = list(reversed(md.uvs[k]))
    # ensure side surface normals point away from the camber line: check one face
    k = NR // 2 * m + (m * 3) // 4
    ps = [Vector(md.verts[q]) for q in md.faces[k]]
    nrm = (ps[1] - ps[0]).cross(ps[3] - ps[0])
    # upper surface faces should point to the suction side (front / +z on average)
    if nrm.z < 0:
        for k in range(NR * m):
            md.faces[k] = tuple(reversed(md.faces[k]))
            md.uvs[k] = list(reversed(md.uvs[k]))
    return md


BLADE_PHI0 = 15.14   # deg, matches the rotor position in the official front photo


def build_impeller():
    md = build_hub()
    for k in range(N_BLADES):
        md.extend(build_blade(BLADE_PHI0 + k * 360.0 / N_BLADES))
    md.name = 'Rotor_Blades'
    return md


# ------------------------------------------------------------------ screws (black self-tapping fan screws, 4 per fan in the box)
def build_screw():
    md = MeshData('screw')
    # pan washer head (dia 7.0 x 2.4) + shank dia 4.6 with a rolled coarse thread (major 5.0)
    prof = [(0.0, 0.0), (3.5, 0.0), (3.5, 0.40), (3.15, 0.75)]
    for k in range(1, 7):
        a = math.radians(90 * k / 6)
        prof.append((1.9 + 1.25 * math.cos(a), 0.75 + 1.65 * math.sin(a)))
    prof.append((0.0, 2.4))
    hd = MeshData('head')
    lathe(hd, prof, 48)
    md.extend(hd)
    # threaded shank: helical radius modulation, z from 0 down to -10
    n, nz = 24, 40
    pitch, L = 1.6, 10.0
    rings = []
    for iz in range(nz + 1):
        z = -L * iz / nz
        ring = []
        for ia in range(n):
            a = 2 * math.pi * ia / n
            ph = ((-z) / pitch + ia / n) % 1.0
            tri = 1 - abs(2 * ph - 1)
            r = 2.05 + 0.45 * tri
            taper = min(1.0, (L + z) / 2.2 + 0.05)   # pointed tip
            r = 0.45 + (r - 0.45) * taper
            ring.append(md.v((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for iz in range(nz):
        for ia in range(n):
            j = (ia + 1) % n
            md.f((rings[iz][ia], rings[iz + 1][ia], rings[iz + 1][j], rings[iz][j]))
    tip = md.v((0, 0, -L - 0.25))
    for ia in range(n):
        md.f((rings[-1][ia], tip, rings[-1][(ia + 1) % n]))
    return md


def phillips_cutter():
    md = MeshData('ph')
    for ang in (0, 90):
        pts = [(-1.9, -0.32), (1.9, -0.32), (1.9, 0.32), (-1.9, 0.32)]
        c = math.cos(math.radians(ang))
        s = math.sin(math.radians(ang))
        rot = [(x * c - y * s, x * s + y * c) for x, y in pts]
        extrude(md, [{'pts': rot, 'rb': 0, 'rf': 0}], 1.2, 3.5)
    return md


# ------------------------------------------------------------------ small embossed marks and interlock features
def build_marks(z_face, front=True):
    md = MeshData('marks')
    h = 0.06
    s = 1 if front else -1

    def prism(pts):
        sub = MeshData('m')
        extrude(sub, [{'pts': pts}], z_face - 0.05 if front else -z_face - h, z_face + h if front else -z_face + 0.05)
        md.extend(sub)
    # "|" mark at the top centre
    prism([(-0.22, 53.4), (0.22, 53.4), (0.22, 55.4), (-0.22, 55.4)])
    # "<|" and "|>" alignment marks at the bottom (positions from the official front/back photos)
    pairs = [(-7.3, -1), (0.2, 1)] if front else [(1.1, 1), (-6.5, -1)]
    for x, dirn in pairs:
        y0, y1 = -55.5, -53.5
        tri_tip = x + dirn * 0.0
        if dirn < 0:
            prism([(x - 1.2, (y0 + y1) / 2), (x + 0.15, y0), (x + 0.15, y1)])
            prism([(x + 0.45, y0), (x + 0.8, y0), (x + 0.8, y1), (x + 0.45, y1)])
        else:
            prism([(x + 1.2, (y0 + y1) / 2), (x - 0.15, y1), (x - 0.15, y0)])
            prism([(x - 0.8, y0), (x - 0.45, y0), (x - 0.45, y1), (x - 0.8, y1)])
    return md


def build_interlock():
    md = MeshData('interlock')
    # bottom edge feet and centre tab (official front photo); pins on the top edge.
    for x0, x1 in ((-51.0, -45.0), (45.0, 51.0)):
        sub = MeshData('foot')
        extrude(sub, [{'pts': [(x0, -6.0), (x1, -6.0), (x1, 6.0), (x0, 6.0)], 'rb': 0.0, 'rf': 0.4, 'segs': 1}], 0.0, 2.5)
        md.extend(sub.transformed(lambda p: (p[0], -HALF + 0.5 - p[2], p[1])))
    sub = MeshData('tab')
    extrude(sub, [{'pts': [(-20.1, -8.0), (4.4, -8.0), (4.4, 8.0), (-20.1, 8.0)], 'rb': 0.0, 'rf': 0.3, 'segs': 1}], 0.0, 1.5)
    md.extend(sub.transformed(lambda p: (p[0], -HALF + 0.5 - p[2], p[1])))
    return md


def build_contacts():
    md = MeshData('Housing_Contacts_Gold')
    for zc in (-4.2, -1.4, 1.4, 4.2):
        pin = MeshData('pin')
        lathe(pin, [(0, 0.0), (0.42, 0.0), (0.42, 1.55), (0.30, 1.75), (0.0, 1.82)], 16)
        md.extend(pin.transformed(lambda p, zc=zc: (19.1 + p[0], HALF - 1.2 + p[2], zc + p[1]), mirror=True))
        pad = MeshData('pad')
        box(pad, 17.8, 20.4, -0.5, 0.5, 0.0, 0.25)
        md.extend(pad.transformed(lambda p, zc=zc: (p[0], -HALF + 1.6 - p[2], zc + p[1])))
    return md
