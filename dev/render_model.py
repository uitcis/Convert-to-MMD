"""把模型与骨架渲染成图，用于肉眼检查 rest pose 是否正常。

用法：
    blender --background --factory-startup --python dev/render_model.py -- <model.blend> <输出目录> [前缀]

输出：<输出目录>/<前缀>_iso.png / _side.png / _front.png
骨架用红色小球（head 位置）+ 细柱（骨长）画出，正交相机，视角按世界 Y 为上。
"""
import os
import sys

import bpy
from mathutils import Vector

BALL_COLOR = (0.95, 0.15, 0.10, 1.0)
MESH_COLOR = (0.78, 0.78, 0.80, 1.0)


def bounding_box(objects):
    low = Vector((1e9, 1e9, 1e9))
    high = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                low[axis] = min(low[axis], point[axis])
                high[axis] = max(high[axis], point[axis])
    return low, high


def make_bone_gizmos(armatures, scale):
    """每根骨画一个小球（head）+ 一根细柱（head→tail）。"""
    radius = max(scale * 0.006, 1e-4)
    for armature in armatures:
        world = armature.matrix_world
        for bone in armature.data.bones:
            head = world @ bone.head_local
            tail = world @ bone.tail_local
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=radius * 1.8, location=head, segments=8, ring_count=6)
            bpy.context.object.color = BALL_COLOR
            direction = tail - head
            if direction.length < 1e-6:
                continue
            bpy.ops.mesh.primitive_cylinder_add(
                radius=radius, depth=direction.length,
                location=(head + tail) * 0.5, vertices=6)
            cylinder = bpy.context.object
            cylinder.color = BALL_COLOR
            cylinder.rotation_mode = 'QUATERNION'
            cylinder.rotation_quaternion = direction.to_track_quat('Z', 'Y')


def main():
    argv = sys.argv
    if "--" not in argv:
        print("用法：-- <model.blend> <输出目录> [前缀]")
        return 1
    rest = argv[argv.index("--") + 1:]
    model = rest[0]
    out_dir = rest[1] if len(rest) > 1 else os.path.dirname(model)
    prefix = rest[2] if len(rest) > 2 else os.path.splitext(
        os.path.basename(model))[0]
    # Blender 解析相对路径不按 shell 的 cwd，统一转绝对路径
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=model)
    scene = bpy.context.scene

    armatures = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    bound = [o for o in bpy.data.objects if o.type == 'MESH'
             and any(m.type == 'ARMATURE' for m in o.modifiers)]
    if not bound:
        bound = [o for o in bpy.data.objects if o.type == 'MESH']
    print(f"armatures={len(armatures)} skinned_meshes={len(bound)}")
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj not in bound:
            obj.hide_render = True
        elif obj.type == 'MESH':
            obj.color = MESH_COLOR

    low, high = bounding_box(bound)
    centre = (low + high) * 0.5
    size = max((high - low))
    print(f"bbox low=({low.x:.3f},{low.y:.3f},{low.z:.3f}) "
          f"high=({high.x:.3f},{high.y:.3f},{high.z:.3f}) size={size:.3f}")
    if size <= 0:
        print("包围盒为空，跳过")
        return 1

    make_bone_gizmos(armatures, size)

    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'OBJECT'
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.film_transparent = False
    # blend 文件里可能存着视频输出（FFMPEG），Blender 5.x 须先切 media_type
    try:
        scene.render.image_settings.media_type = 'IMAGE'
    except (AttributeError, TypeError):
        pass
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.view_settings.view_transform = 'Standard'

    camera_data = bpy.data.cameras.new("DiagCam")
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = size * 1.35
    camera = bpy.data.objects.new("DiagCam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    shots = {
        "iso": Vector((2.0, -2.0, 1.2)),
        "side": Vector((2.4, 0.15, 0.25)),
        "front": Vector((0.15, -2.4, 0.25)),
    }
    for name, direction in shots.items():
        unit = direction.normalized()
        camera.location = centre + unit * size * 4.0
        camera.rotation_mode = 'QUATERNION'
        camera.rotation_quaternion = (-unit).to_track_quat('-Z', 'Y')
        scene.render.filepath = os.path.join(out_dir, f"{prefix}_{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"WROTE {scene.render.filepath}")

    # X 光：模型半透明，露出内部骨架
    scene.display.shading.show_xray = True
    scene.display.shading.xray_alpha = 0.22
    unit = shots["iso"].normalized()
    camera.location = centre + unit * size * 4.0
    camera.rotation_quaternion = (-unit).to_track_quat('-Z', 'Y')
    scene.render.filepath = os.path.join(out_dir, f"{prefix}_xray.png")
    bpy.ops.render.render(write_still=True)
    print(f"WROTE {scene.render.filepath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
