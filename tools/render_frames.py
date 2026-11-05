"""Render listed frames; a frame whose PNG exists is skipped, so a stopped run resumes.
Run: blender -b build/scene.blend --python tools/render_frames.py -- OUTDIR FRAME [FRAME...] [--samples N] [--scale PCT] [--cpu]"""
import os
import sys
import time
import bpy

a = sys.argv[sys.argv.index("--") + 1:]
out, sc = os.path.abspath(a[0]), bpy.context.scene  # Blender sent a relative path to the C: drive root
if "--samples" in a:
    i = a.index("--samples"); sc.cycles.samples = int(a[i + 1]); del a[i:i + 2]
if "--scale" in a:
    i = a.index("--scale"); sc.render.resolution_percentage = int(a[i + 1]); del a[i:i + 2]
if "--cpu" in a:
    a.remove("--cpu"); sc.cycles.device = "CPU"; sc.cycles.denoiser = "OPENIMAGEDENOISE"
else:
    p = bpy.context.preferences.addons["cycles"].preferences
    p.compute_device_type = "OPTIX"; p.get_devices()
    for d in p.devices:
        d.use = d.type == "OPTIX"
for f in a[1:]:
    path = f"{out}/f{int(f):04d}.png"
    if os.path.exists(path):
        continue
    t = time.time(); sc.frame_set(int(f)); sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"TIMED frame {f}: {time.time() - t:.1f} s", flush=True)
