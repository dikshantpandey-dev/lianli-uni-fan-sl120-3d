"""Build the Lian Li UNI FAN SL120 (black, UF-SL120-1B) in Blender 4.5 and export it.

    blender -b --factory-startup -P build_sl120.py -- <project_dir>

Creates <project_dir>/blender/LianLi_UNI_FAN_SL120.blend and the glTF exports.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sl120_geom as G  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
PROJ = os.path.abspath(argv[0] if argv else os.path.join(HERE, '..', '..'))
TEX = os.path.join(PROJ, 'textures')
UV_TILE = 25.6  # mm per UV unit for tileable textures

# model (mm, Y-up, +Z = front) -> Blender (m, Z-up, front faces -Y)
CONV = Matrix.Rotation(math.radians(90.0), 4, 'X') @ Matrix.Scale(0.001, 4)


def to_model(v):
    return Vector((v.x, v.z, -v.y)) * 1000.0


# ------------------------------------------------------------------ scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = 'SL120'
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'MILLIMETERS'
scene.render.fps = 30
coll_root = scene.collection


# ------------------------------------------------------------------ materials
def img(name, colorspace):
    path = os.path.join(TEX, name)
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    return m, nt, bsdf


def tex_node(nt, image, x, y):
    n = nt.nodes.new('ShaderNodeTexImage')
    n.image = image
    n.location = (x, y)
    return n


def link_normal(nt, bsdf, image, strength):
    t = tex_node(nt, image, -700, -450)
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nm.location = (-350, -450)
    nm.inputs['Strength'].default_value = strength
    nt.links.new(t.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])


def link_orm(nt, bsdf, image, rough_fac=None, metal=True):
    t = tex_node(nt, image, -900, 0)
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    sep.location = (-600, 0)
    nt.links.new(t.outputs['Color'], sep.inputs['Color'])
    if rough_fac is None:
        nt.links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
    else:
        mul = nt.nodes.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        mul.location = (-350, 0)
        mul.inputs[1].default_value = rough_fac
        nt.links.new(sep.outputs['Green'], mul.inputs[0])
        nt.links.new(mul.outputs[0], bsdf.inputs['Roughness'])
    if metal:
        nt.links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c) + (1.0,)


IM_GRAIN_N = img('T_PlasticGrain_N.png', 'Non-Color')
IM_GRAIN_ORM = img('T_PlasticGrain_ORM.png', 'Non-Color')


def plastic(name, color, rough, nstrength):
    m, nt, b = new_mat(name)
    b.inputs['Base Color'].default_value = srgb(color)
    b.inputs['Metallic'].default_value = 0.0
    link_orm(nt, b, IM_GRAIN_ORM, rough_fac=rough, metal=False)
    link_normal(nt, b, IM_GRAIN_N, nstrength)
    b.inputs['Specular IOR Level'].default_value = 0.5
    return m


MAT = {}
MAT['frame'] = plastic('MAT_Frame_PBT_Black', '#303134', 0.62, 0.55)
MAT['blades'] = plastic('MAT_Blades_PBT_Black', '#3c3d40', 0.58, 0.45)
MAT['rubber'] = plastic('MAT_CornerPad_Rubber_Black', '#1d1d1f', 0.86, 0.35)

m, nt, b = new_mat('MAT_HubCap_SpunAluminium')
t = tex_node(nt, img('T_HubCap_BaseColor.png', 'sRGB'), -900, 300)
nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
link_orm(nt, b, img('T_HubCap_ORM.png', 'Non-Color'))
link_normal(nt, b, img('T_HubCap_N.png', 'Non-Color'), 1.0)
tan = nt.nodes.new('ShaderNodeTangent')
tan.direction_type = 'RADIAL'
tan.axis = 'Y'
tan.location = (-350, -750)
nt.links.new(tan.outputs['Tangent'], b.inputs['Tangent'])
b.inputs['Anisotropic'].default_value = 0.0   # raised to 0.85 for Cycles renders (render script)
MAT['cap'] = m

m, nt, b = new_mat('MAT_SidePlate_Aluminium_BlackAnodized')
b.inputs['Base Color'].default_value = (0.032, 0.032, 0.034, 1)
b.inputs['Metallic'].default_value = 1.0
b.inputs['Roughness'].default_value = 0.30
link_normal(nt, b, img('T_AluBrushed_N.png', 'Non-Color'), 0.6)
MAT['alu'] = m
m, nt, b = new_mat('MAT_SidePlate_Aluminium_DiamondCut')
b.inputs['Base Color'].default_value = (0.92, 0.92, 0.92, 1)
b.inputs['Metallic'].default_value = 1.0
b.inputs['Roughness'].default_value = 0.10
MAT['alu_cut'] = m

m, nt, b = new_mat('MAT_RGB_Diffuser_PC')
b.inputs['Base Color'].default_value = (0.80, 0.80, 0.82, 1)
b.inputs['Roughness'].default_value = 0.38
b.inputs['IOR'].default_value = 1.585
b.inputs['Transmission Weight'].default_value = 0.35
b.inputs['Subsurface Weight'].default_value = 0.6
b.inputs['Subsurface Radius'].default_value = (1.0, 1.0, 1.0)
b.inputs['Subsurface Scale'].default_value = 0.0015
t = tex_node(nt, img('T_RGB_Emissive.png', 'sRGB'), -700, -150)
t.extension = 'REPEAT'
nt.links.new(t.outputs['Color'], b.inputs['Emission Color'])
b.inputs['Emission Strength'].default_value = 4.0
MAT['rgb'] = m

m, nt, b = new_mat('MAT_MotorLabel')
t = tex_node(nt, img('T_MotorLabel_BaseColor.png', 'sRGB'), -700, 300)
nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
b.inputs['Roughness'].default_value = 0.55
MAT['label'] = m

m, nt, b = new_mat('MAT_Contacts_Gold')
b.inputs['Base Color'].default_value = (1.0, 0.766, 0.336, 1)
b.inputs['Metallic'].default_value = 1.0
b.inputs['Roughness'].default_value = 0.25
MAT['gold'] = m

m, nt, b = new_mat('MAT_Screw_BlackZinc')
b.inputs['Base Color'].default_value = (0.045, 0.045, 0.05, 1)
b.inputs['Metallic'].default_value = 0.85
b.inputs['Roughness'].default_value = 0.38
MAT['screw'] = m

m, nt, b = new_mat('MAT_Wire_PVC_Black')
b.inputs['Base Color'].default_value = (0.018, 0.018, 0.02, 1)
b.inputs['Roughness'].default_value = 0.32
MAT['wire'] = m


# ------------------------------------------------------------------ mesh conversion
def box_uv_model(p, n):
    ax = max(range(3), key=lambda i: abs(n[i]))
    x, y, z = p
    if ax == 2:
        u, v = (x, y) if n[2] > 0 else (-x, y)
    elif ax == 0:
        u, v = (-z, y) if n[0] > 0 else (z, y)
    else:
        u, v = (x, -z) if n[1] > 0 else (x, z)
    return (u / UV_TILE, v / UV_TILE)


def face_normal_model(md, fc):
    ps = [Vector(md.verts[i]) for i in fc]
    nrm = Vector((0, 0, 0))
    for i in range(len(ps)):
        nrm += ps[i].cross(ps[(i + 1) % len(ps)])
    return nrm.normalized() if nrm.length > 0 else Vector((0, 0, 1))


def make_object(md, mats, parent=None, name=None, sharp_angle=32.0):
    name = name or md.name
    me = bpy.data.meshes.new(name)
    verts = [(CONV @ Vector(p)) for p in md.verts]
    me.from_pydata([tuple(v) for v in verts], [], [list(f) for f in md.faces])
    uvl = me.uv_layers.new(name='UVMap')
    li = 0
    for pi, poly in enumerate(me.polygons):
        uv = md.uvs[pi]
        fc = md.faces[pi]
        if uv is None:
            nrm = face_normal_model(md, fc)
            uv = [box_uv_model(md.verts[i], nrm) for i in fc]
        for k, loop_index in enumerate(poly.loop_indices):
            uvl.data[loop_index].uv = uv[k]
        poly.material_index = md.mats[pi]
        poly.use_smooth = True
    me.validate(clean_customdata=False)
    me.update()
    for mt in mats:
        me.materials.append(mt)
    ob = bpy.data.objects.new(name, me)
    coll_root.objects.link(ob)
    if parent:
        ob.parent = parent
    me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    return ob


def apply_boolean(ob, cutters, op='DIFFERENCE'):
    for c in cutters:
        mod = ob.modifiers.new('bool_' + c.name, 'BOOLEAN')
        mod.operation = op
        mod.solver = 'EXACT'
        mod.object = c
        bpy.context.view_layer.objects.active = ob
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(c, do_unlink=True)


def box_uv_object(ob):
    """Re-project tileable UVs (after booleans) in model space."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        n = to_model(f.normal)
        n.normalize()
        for lp in f.loops:
            p = to_model(lp.vert.co)
            lp[uvl].uv = box_uv_model((p.x, p.y, p.z), n)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(32.0))


def empty(name, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'PLAIN_AXES'
    e.empty_display_size = 0.02
    coll_root.objects.link(e)
    if parent:
        e.parent = parent
    return e


# ------------------------------------------------------------------ build
root = empty('SL120')
grp_housing = empty('Housing', root)
grp_motor = empty('Motor', root)
grp_rotor = empty('Rotor', root)          # pivot on the rotation axis (glTF +Z)
grp_rgb = empty('RGB', root)
grp_screws = empty('Screws', root)

# --- frame body + bosses + struts + interlock + marks
frame = G.build_frame_body()
struts, wires = G.build_struts()
frame.extend(struts)
frame.extend(G.build_interlock())
frame.extend(G.build_marks(G.Z_FACE, True))
frame.extend(G.build_marks(G.Z_FACE, False))
frame.name = 'Housing_Frame'
ob_frame = make_object(frame, [MAT['frame']], grp_housing)

# channels for the diffusers (front/back, left/right) + connector pockets
cut_objs = []
outline = G.channel_cutter_outline()
for sx in (1, -1):
    for sz in (1, -1):
        c = G.MeshData('cut')
        G.extrude(c, [{'pts': [(sx * x, y) for x, y in outline]}], G.CHANNEL_Z_BOT, G.Z_FACE + 1.0)
        c = c.transformed(lambda p, sz=sz: (p[0], p[1], sz * p[2]), mirror=(sz < 0))
        cut_objs.append(make_object(c, [], None, name='cut_ch_%d_%d' % (sx, sz)))
pin_win = G.MeshData('pinwin')
G.box(pin_win, 17.2, 21.0, -6.0, 6.0, 0.0, 1.0)
pin_win = pin_win.transformed(lambda p: (p[0], G.HALF - 1.2 + p[2] * 3.0, p[1]), mirror=True)
cut_objs.append(make_object(pin_win, [], None, name='cut_pinwin'))
rec_win = G.MeshData('recwin')
G.box(rec_win, 17.2, 21.0, -6.0, 6.0, 0.0, 1.0)
rec_win = rec_win.transformed(lambda p: (p[0], -G.HALF + 1.6 - p[2] * 3.0, p[1]))
cut_objs.append(make_object(rec_win, [], None, name='cut_recwin'))
apply_boolean(ob_frame, cut_objs)
box_uv_object(ob_frame)

# --- motor
ob_motor = make_object(G.build_motor_housing(), [MAT['frame']], grp_motor, name='Motor_Housing')
ob_label = make_object(G.build_label(), [MAT['label']], grp_motor, name='Motor_Label', sharp_angle=1.0)
ob_wires = make_object(wires, [MAT['wire']], grp_motor, name='Motor_Wires', sharp_angle=60.0)

# --- corner pads (8)
pad = G.build_pad()
pads = G.MeshData('Housing_CornerPads')
for sx in (1, -1):
    for sy in (1, -1):
        for sz in (1, -1):
            mirror = (sx * sy * sz) < 0
            pads.extend(pad.transformed(lambda p, sx=sx, sy=sy, sz=sz: (-sx * p[0], sy * p[1], sz * p[2]), mirror=not mirror))
make_object(pads, [MAT['rubber']], grp_housing)

# --- side plates (aluminium) and gold contacts
plates = G.MeshData('Housing_SidePlates_Aluminium')
pr = G.side_part(G.plate_shape(), 0, 1, 0.5)
for sx in (1, -1):
    part = pr.transformed(lambda p, sx=sx: (sx * p[0], p[1], p[2]), mirror=(sx < 0))
    base = len(plates.faces)
    plates.extend(part)
for k, fc in enumerate(plates.faces):
    plates.uvs[k] = [(plates.verts[i][1] / UV_TILE, plates.verts[i][2] / UV_TILE) for i in fc]
make_object(plates, [MAT['alu'], MAT['alu_cut']], grp_housing, sharp_angle=30.0)
make_object(G.build_contacts(), [MAT['gold']], grp_housing, name='Housing_Contacts_Gold')

# --- RGB diffusers (front strip, back strip, side bands) with U = position along the light loop
for side, sx, (u0, u1) in (('Left', -1, (0.0, 0.5)), ('Right', 1, (1.0, 0.5))):
    md = G.MeshData('RGB_Diffuser_' + side)
    strip = G.build_strip(u0, u1)
    if sx > 0:
        strip = strip.transformed(lambda p: (-p[0], p[1], p[2]), mirror=True)
    md.extend(strip)
    md.extend(strip.transformed(lambda p: (p[0], p[1], -p[2]), mirror=True))
    for front in (True, False):
        band = G.side_part(G.band_shape(front), 0, 0, 0.35)
        if sx < 0:
            band = band.transformed(lambda p: (-p[0], p[1], p[2]), mirror=True)
        zlo, zhi = (7.0, 11.85)
        for k, fc in enumerate(band.faces):
            uvs = []
            for i in fc:
                y, z = band.verts[i][1], band.verts[i][2]
                u = (0.1 + 0.3 * (38.7 - y) / 77.4) if sx < 0 else (0.6 + 0.3 * (y + 38.7) / 77.4)
                uvs.append((u, (abs(z) - zlo) / (zhi - zlo)))
            band.uvs[k] = uvs
        md.extend(band)
    make_object(md, [MAT['rgb']], grp_rgb, sharp_angle=35.0)

# --- rotor
ob_blades = make_object(G.build_impeller(), [MAT['blades']], grp_rotor, name='Rotor_Blades', sharp_angle=48.0)
ob_cap = make_object(G.build_cap(), [MAT['cap']], grp_rotor, name='Rotor_HubCap', sharp_angle=40.0)

# --- screws (4 black self-tapping fan screws, heads seated on the front pads)
sc = G.build_screw()
for name, sx, sy in (('Screw_TL', -1, 1), ('Screw_TR', 1, 1), ('Screw_BL', -1, -1), ('Screw_BR', 1, -1)):
    md = sc.transformed(lambda p, sx=sx, sy=sy: (p[0] + sx * G.HOLE_C, p[1] + sy * G.HOLE_C, p[2] + G.Z_PAD))
    md.name = name
    ob = make_object(md, [MAT['screw']], grp_screws, sharp_angle=50.0)
    ph = G.phillips_cutter().transformed(lambda p, sx=sx, sy=sy: (p[0] + sx * G.HOLE_C, p[1] + sy * G.HOLE_C, p[2] + G.Z_PAD))
    apply_boolean(ob, [make_object(ph, [], None, name='cut_' + name)])
    ob.data.set_sharp_from_angle(angle=math.radians(50.0))

# ------------------------------------------------------------------ rotor spin animation (1 rev / s, CCW seen from the front)
scene.frame_start, scene.frame_end = 1, 31
grp_rotor.rotation_mode = 'XYZ'
for fr, ang in ((1, 0.0), (31, -2 * math.pi)):
    grp_rotor.rotation_euler = (0.0, ang, 0.0)
    grp_rotor.keyframe_insert('rotation_euler', index=1, frame=fr)
act = grp_rotor.animation_data.action
act.name = 'Rotor_Spin'
for fc in act.fcurves if hasattr(act, 'fcurves') else []:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
    fc.modifiers.new('CYCLES')
try:
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for fc in cb.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = 'LINEAR'
except AttributeError:
    pass
scene.frame_set(1)

# ------------------------------------------------------------------ stats
tri = 0
for ob in scene.objects:
    if ob.type == 'MESH':
        ob.data.calc_loop_triangles()
        n = len(ob.data.loop_triangles)
        tri += n
        dims = ob.dimensions * 1000
        print('OBJ %-36s tris %6d  dims(mm) %.2f x %.2f x %.2f' % (ob.name, n, dims.x, dims.y, dims.z))
print('TOTAL TRIS', tri)

os.makedirs(os.path.join(PROJ, 'blender'), exist_ok=True)
blend = os.path.join(PROJ, 'blender', 'LianLi_UNI_FAN_SL120.blend')
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True, relative_remap=True)
print('SAVED', blend)
