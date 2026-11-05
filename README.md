# stitches-blender-remake

A 31-second vertical video of a stitched leg wound healing, built as real 3D in Blender. No AI video generator makes any picture. Same beats as a public reference short, with new 3D assets, new script, and new voice.

**Live write-up (development journey):** https://az9713.github.io/stitches-blender-remake/DEVELOPMENT-JOURNEY.html

**Watch the video:** https://az9713.github.io/stitches-blender-remake/stitches_final_v2.mp4 (also embedded at the top of the journey page).

## What is in this repo
| File | Content |
|---|---|
| `DEVELOPMENT-JOURNEY.html` | How the video was made: stack, decisions, iterations, errors, and the unknown unknowns. |
| `tools/measure.py` | Measures a video per frame: brightness, contrast, saturation, sideways motion, zoom. |
| `tools/build_scene.py` | Builds the Blender scene (run headless). |
| `tools/render_frames.py` | Resumable Cycles frame renderer. |
| `tools/mix.py` | ffmpeg sound mix. |
| `tools/post.py` | Colour grade, upscale, and H.264 encode. |
| `stitches_final_v2.mp4` | The finished film (1296x2304, 31 s, 19.9 MB). |
| `beats.md`, `HANDOFF.md`, `README.txt` | Beat sheet, resume notes, and the source brief. |

## What is not in this repo
Rendered frames, the first version of the video (165 MB, above the GitHub file limit), the Blender scene, the audio, the reference video, and the tutorial transcript stay local. The reference is the work of Zack D. Films (`ttuKeS5k4Uo`). The method follows a tutorial by Omi (`_fIoJ_ywGfY`).
