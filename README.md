# stitches-blender-remake

A 31-second vertical video of a stitched leg wound healing, built as real 3D in Blender. No AI video generator makes any picture. Same beats as a public reference short, with new 3D assets, new script, and new voice.

**Live write-up (development journey):** https://az9713.github.io/stitches-blender-remake/DEVELOPMENT-JOURNEY.html

## What is in this repo
| File | Content |
|---|---|
| `DEVELOPMENT-JOURNEY.html` | How the video was made: stack, decisions, iterations, errors, and the unknown unknowns. |
| `tools/measure.py` | Measures a video per frame: brightness, contrast, saturation, sideways motion, zoom. |
| `tools/build_scene.py` | Builds the Blender scene (run headless). |
| `tools/render_frames.py` | Resumable Cycles frame renderer. |
| `tools/mix.py` | ffmpeg sound mix. |
| `tools/post.py` | Colour grade, upscale, and H.264 encode. |
| `beats.md`, `HANDOFF.md`, `README.txt` | Beat sheet, resume notes, and the source brief. |

## What is not in this repo
Rendered frames, the finished videos, the Blender scene, the audio, the reference video, and the tutorial transcript stay local. The reference is the work of Zack D. Films (`ttuKeS5k4Uo`). The method follows a tutorial by Omi (`_fIoJ_ywGfY`).
