"""Export the SL120 .blend to web formats.

    blender -b LianLi_UNI_FAN_SL120.blend -P export_sl120.py -- <project_dir>

Writes glb/LianLi_UNI_FAN_SL120.glb (embedded textures) and gltf/ (separate .gltf/.bin/textures).
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
PROJ = os.path.abspath(argv[0])
scene = bpy.context.scene

# web-tuned values (Cycles-only extras are not part of glTF anyway)
rgb = bpy.data.materials['MAT_RGB_Diffuser_PC'].node_tree.nodes['Principled BSDF']
rgb.inputs['Emission Strength'].default_value = 3.0
bpy.data.materials['MAT_HubCap_SpunAluminium'].node_tree.nodes['Principled BSDF'].inputs['Anisotropic'].default_value = 0.0

root = bpy.data.objects['SL120']
root['product'] = 'Lian Li UNI FAN SL120 RGB (black, UF-SL120-1B)'
root['units'] = 'metres (1 unit = 1 m); frame 0.120 x 0.120 x 0.025'
root['rotor_node'] = 'Rotor: spin about local +Z, positive = counter-clockwise seen from the front (intake)'
root['rgb_nodes'] = 'RGB_Diffuser_Left / RGB_Diffuser_Right; emissive U coordinate = position around the light loop (0..1)'
root['fan_speed_rpm'] = '800-1900 (official spec)'
bpy.data.objects['Rotor']['spin_axis'] = '+Z (glTF), counter-clockwise seen from the front'

common = dict(
    use_selection=False,
    export_yup=True,
    export_apply=True,
    export_texcoords=True,
    export_normals=True,
    export_tangents=False,
    export_materials='EXPORT',
    export_image_format='AUTO',
    export_cameras=False,
    export_lights=False,
    export_extras=True,
    export_animations=True,
    export_animation_mode='ACTIONS',
    export_force_sampling=True,
)
os.makedirs(os.path.join(PROJ, 'glb'), exist_ok=True)
os.makedirs(os.path.join(PROJ, 'gltf'), exist_ok=True)
glb = os.path.join(PROJ, 'glb', 'LianLi_UNI_FAN_SL120.glb')
bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', **common)
print('EXPORTED', glb, os.path.getsize(glb))
gltf = os.path.join(PROJ, 'gltf', 'LianLi_UNI_FAN_SL120.gltf')
bpy.ops.export_scene.gltf(filepath=gltf, export_format='GLTF_SEPARATE', export_texture_dir='textures', **common)
print('EXPORTED', gltf)
