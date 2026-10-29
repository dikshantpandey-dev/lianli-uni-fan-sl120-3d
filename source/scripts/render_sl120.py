"""Cycles product renders + turntable for the SL120 model.

    blender -b <blend> -P render_sl120.py -- <project_dir> <mode> [samples] [shot,shot,...]
mode: stills | turntable
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
PROJ = os.path.abspath(argv[0])
MODE = argv[1] if len(argv) > 1 else 'stills'
SAMPLES = int(argv[2]) if len(argv) > 2 else 128
ONLY = argv[3].split(',') if len(argv) > 3 and argv[3] else None
OUT = os.path.join(PROJ, 'renders')
os.makedirs(OUT, exist_ok=True)
HDRI = os.path.join(PROJ, 'source', 'assets', 'studio_small_09_2k.hdr')

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = SAMPLES
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.02
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.cycles.max_bounces = 10
scene.cycles.transmission_bounces = 8
scene.cycles.caustics_reflective = False
scene.cycles.caustics_refractive = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.render.threads_mode = 'AUTO'

# Cycles-only material extras
cap = bpy.data.materials['MAT_HubCap_SpunAluminium']
cap.node_tree.nodes['Principled BSDF'].inputs['Anisotropic'].default_value = 0.85
rgb_bsdf = bpy.data.materials['MAT_RGB_Diffuser_PC'].node_tree.nodes['Principled BSDF']

# ------------------------------------------------------------------ world: HDRI light, solid backdrop for camera rays
world = bpy.data.worlds.new('Studio')
scene.world = world
world.use_nodes = True
wn = world.node_tree
for n in list(wn.nodes):
    wn.nodes.remove(n)
env = wn.nodes.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load(HDRI, check_existing=True)
mapping = wn.nodes.new('ShaderNodeMapping')
texco = wn.nodes.new('ShaderNodeTexCoord')
wn.links.new(texco.outputs['Generated'], mapping.inputs['Vector'])
wn.links.new(mapping.outputs['Vector'], env.inputs['Vector'])
bg_light = wn.nodes.new('ShaderNodeBackground')
wn.links.new(env.outputs['Color'], bg_light.inputs['Color'])
bg_gloss = wn.nodes.new('ShaderNodeBackground')       # what reflections see (product-photo 'reflector cards')
wn.links.new(env.outputs['Color'], bg_gloss.inputs['Color'])
bg_cam = wn.nodes.new('ShaderNodeBackground')
lp = wn.nodes.new('ShaderNodeLightPath')
mixg = wn.nodes.new('ShaderNodeMixShader')
wn.links.new(lp.outputs['Is Glossy Ray'], mixg.inputs['Fac'])
wn.links.new(bg_light.outputs['Background'], mixg.inputs[1])
wn.links.new(bg_gloss.outputs['Background'], mixg.inputs[2])
mix = wn.nodes.new('ShaderNodeMixShader')
wn.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
wn.links.new(mixg.outputs['Shader'], mix.inputs[1])
wn.links.new(bg_cam.outputs['Background'], mix.inputs[2])
outn = wn.nodes.new('ShaderNodeOutputWorld')
wn.links.new(mix.outputs['Shader'], outn.inputs['Surface'])


def set_world(strength, bg_rgb, rot_z_deg=0.0, gloss=None):
    bg_light.inputs['Strength'].default_value = strength
    bg_gloss.inputs['Strength'].default_value = strength * 4.0 if gloss is None else gloss
    bg_cam.inputs['Color'].default_value = (*bg_rgb, 1.0)
    bg_cam.inputs['Strength'].default_value = 1.0
    mapping.inputs['Rotation'].default_value = (0, 0, math.radians(rot_z_deg))


# ------------------------------------------------------------------ lights (softboxes) and floor
def area(name, loc, size, energy, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.shape = 'RECTANGLE'
    ld.size, ld.size_y = size
    ld.energy = energy
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(ob)
    ob.location = loc
    tgt = Vector((0, 0, 0))
    ob.rotation_euler = (tgt - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob


key = area('Key', (-0.35, -0.45, 0.40), (0.35, 0.25), 28.0)
fill = area('Fill', (0.45, -0.35, 0.05), (0.40, 0.40), 8.0)
rim = area('Rim', (0.10, 0.45, 0.35), (0.30, 0.10), 18.0)
refl = area('Reflector', (0, -1.2, 0), (0.9, 0.9), 0.0)

floor_me = bpy.data.meshes.new('Floor')
s = 3.0
floor_me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [[0, 1, 2, 3]])
floor = bpy.data.objects.new('Floor', floor_me)
scene.collection.objects.link(floor)
fm = bpy.data.materials.new('Floor')
fm.use_nodes = True
fb = fm.node_tree.nodes['Principled BSDF']
fb.inputs['Base Color'].default_value = (0.02, 0.02, 0.022, 1)
fb.inputs['Roughness'].default_value = 0.35
floor_me.materials.append(fm)
floor.visible_glossy = False

# ------------------------------------------------------------------ camera
cam_data = bpy.data.cameras.new('Cam')
cam = bpy.data.objects.new('Cam', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
target = bpy.data.objects.new('CamTarget', None)
scene.collection.objects.link(target)
trk = cam.constraints.new('TRACK_TO')
trk.target = target
trk.track_axis = 'TRACK_NEGATIVE_Z'
trk.up_axis = 'UP_Y'

root = bpy.data.objects['SL120']
rotor = bpy.data.objects['Rotor']
screws = bpy.data.objects['Screws']


def place_cam(az_deg, el_deg, dist, lens=100.0, tgt=(0, 0, 0), ortho=None):
    a, e = math.radians(az_deg), math.radians(el_deg)
    # az measured from the front (-Y) toward +X
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    target.location = tgt
    cam.location = Vector(tgt) + d * dist
    if ortho:
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = ortho
    else:
        cam_data.type = 'PERSP'
        cam_data.lens = lens
    cam_data.clip_start = 0.005
    cam_data.clip_end = 20


def screws_visible(v):
    for ob in screws.children:
        ob.hide_render = not v


def shot(name, res, emission, world_strength, bg, floor_on, cam_args, screws_on=True, rot_world=0.0,
         lights=(6.0, 2.0, 6.0), reflector=0.0, view=('AgX', 'AgX - Punchy'), bg_strength=1.0,
         fan_rot=(0, 0, 0), rotor_deg=0.0, lift=0.0, exposure=0.0, gloss=None):
    if ONLY and name not in ONLY:
        return
    scene.render.resolution_x, scene.render.resolution_y = res
    rgb_bsdf.inputs['Emission Strength'].default_value = emission
    set_world(world_strength, bg, rot_world, gloss)
    bg_cam.inputs['Strength'].default_value = bg_strength
    scene.view_settings.view_transform, scene.view_settings.look = view
    scene.view_settings.exposure = exposure
    floor.hide_render = not floor_on
    for l, e in zip((key, fill, rim), lights):
        l.hide_render = e <= 0
        l.data.energy = max(e, 0.0)
    root.rotation_euler = tuple(math.radians(v) for v in fan_rot)
    root.location = (0, 0, lift)
    rotor.rotation_euler = (0, math.radians(-rotor_deg), 0)
    screws_visible(screws_on)
    place_cam(*cam_args)
    # large soft reflector behind the camera (gives the spun-aluminium cap its bright sheen)
    refl.hide_render = reflector <= 0
    refl.data.energy = reflector
    refl.location = cam.location + (cam.location - target.location).normalized() * 0.25
    refl.rotation_euler = (target.location - refl.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(OUT, name + '.png')
    if MODE == 'setup':
        return
    bpy.ops.render.render(write_still=True)
    print('RENDERED', name)


scene.frame_set(1)
LIFT = 0.0605  # fan standing on its bottom feet on the floor (y=-62 mm)

if MODE == 'setup':
    # leave the hero RGB studio configured in the saved .blend (F12 renders it)
    ONLY = ['sl120_hero_rgb']
if MODE in ('stills', 'setup'):
    WHITE = dict(view=('Standard', 'None'), bg_strength=2.0, gloss=2.2)
    RGBV = dict(view=('Standard', 'None'), gloss=0.9)
    DARK = (0.004, 0.004, 0.005)
    # 1/2: orthographic comparison views (no RGB, white backdrop, like the official catalogue photos)
    shot('sl120_front_ortho', (1400, 1400), 0.0, 0.35, (1, 1, 1), False, (0, 0, 1.0, 100, (0, 0, 0), 0.135),
         screws_on=False, lights=(3.0, 1.2, 0.0), reflector=1.5, **WHITE)
    shot('sl120_back_ortho', (1400, 1400), 0.0, 0.35, (1, 1, 1), False, (180, 0, 1.0, 100, (0, 0, 0), 0.135),
         screws_on=False, lights=(3.0, 1.2, 0.0), reflector=1.5, **WHITE)
    # 3: hero, RGB on, dark studio
    shot('sl120_hero_rgb', (1920, 1280), 2.4, 0.12, DARK, True,
         (-32, 18, 0.62, 85, (0, 0, LIFT)), lift=LIFT, lights=(2.0, 0.5, 6.0), reflector=1.5, rot_world=40, **RGBV)
    # 4: hero, RGB off, light studio
    shot('sl120_hero_studio', (1920, 1280), 0.0, 0.35, (1, 1, 1), False,
         (28, 16, 0.62, 85, (0, 0, 0)), lights=(4.0, 1.5, 4.0), reflector=1.5, **WHITE)
    # 5: back three-quarter, RGB on
    shot('sl120_back_rgb', (1920, 1280), 2.4, 0.12, DARK, True,
         (148, 20, 0.62, 85, (0, 0, LIFT)), lift=LIFT, screws_on=False, lights=(2.0, 0.5, 6.0), reflector=1.5, rot_world=200, **RGBV)
    # 6: side wall detail (aluminium plate + side diffusers), RGB on
    shot('sl120_side_detail_rgb', (1920, 1280), 2.4, 0.12, DARK, True,
         (72, 14, 0.32, 85, (0.040, 0, LIFT + 0.012)), lift=LIFT, screws_on=False, lights=(2.0, 0.5, 6.0), reflector=1.5, rot_world=120, **RGBV)
    # 7: hub cap close-up
    shot('sl120_hub_closeup', (1600, 1600), 0.0, 0.35, (1, 1, 1), False,
         (-20, 22, 0.16, 100, (0, -0.011, 0)), screws_on=False, lights=(3.0, 1.0, 2.0), reflector=1.5, **WHITE)

if MODE == 'setup':
    scene.cycles.samples = 128
    scene.render.filepath = '//../renders/'
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath, compress=True)
    print('SAVED SETUP', bpy.data.filepath)

elif MODE == 'turntable':
    frames = int(argv[4]) if len(argv) > 4 else 72
    start = int(argv[5]) if len(argv) > 5 else 0
    end = int(argv[6]) if len(argv) > 6 else frames
    tdir = os.path.join(OUT, 'turntable_frames')
    os.makedirs(tdir, exist_ok=True)
    scene.render.resolution_x = scene.render.resolution_y = 720
    rgb_bsdf.inputs['Emission Strength'].default_value = 2.4
    set_world(0.12, (0.004, 0.004, 0.005), 40, 0.9)
    scene.view_settings.view_transform, scene.view_settings.look = 'Standard', 'None'
    floor.hide_render = False
    key.data.energy, fill.data.energy, rim.data.energy = 2.5, 0.6, 7.0
    refl.data.energy = 2.5
    refl.location = (0, -1.2, 0.3)
    refl.rotation_euler = (Vector((0, 0, LIFT)) - refl.location).to_track_quat('-Z', 'Y').to_euler()
    screws_visible(False)
    root.location = (0, 0, LIFT)
    place_cam(0, 14, 0.62, 85, (0, 0, LIFT))
    for i in range(start, end):
        root.rotation_euler = (0, 0, math.radians(360.0 * i / frames))
        rotor.rotation_euler = (0, math.radians(-(i * 37.0)), 0)
        scene.render.filepath = os.path.join(tdir, 'tt_%03d.png' % i)
        bpy.ops.render.render(write_still=True)
        print('FRAME', i)
