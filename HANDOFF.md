# HANDOFF: stitches short remake

**Read this first in a new session. Then read `beats.md`.** Global rules are in the global CLAUDE.md.

Goal: reproduce Zack D. Films "How Stitches Work" (`ttuKeS5k4Uo`) in real Blender. The source list is `README.txt` and `transcript.txt`.

## The user's decisions (2026-11-03)
- Same beats, own words. New 3D assets, script, and voice. Do not reuse his frames or audio.
- Audio: ElevenLabs. Render: Cycles, 1080x1920, upscaled to 1296x2304. Leg: free MPFB human.
- On 2026-11-04 the user asked: "save what you have and run the new pass."

## Current state (verified 2026-11-04)
- **Version 1 exists:** `stitches_final.mp4`, H.264 CRF 16, 164.9 MB, 929 frames (`-shortest` cut frame 930), 31.00 s. Too dark and too saturated: see the table. Keep this file. The user has not yet given notes on it.
- **Render complete:** all 930 PNGs are in `build/frames/`. No new render is needed for a colour change. Scene: `build/scene.blend`.
- **Sound complete:** `audio/mix.wav` from `tools/mix.py`, music take A. In version 1: -12.6 LUFS, LRA 2.5 LU, peak -0.8 dBFS. Reference: -12.0 LUFS, LRA 1.6 LU, +1.6 dBFS. Nobody has listened to it, because the agent can only measure audio.
- **Version 2 finished (2026-11-04):** `stitches_final_v2.mp4`, H.264 CRF 20 preset medium, 19.9 MB, 930 frames, video 31.031 s, audio 31.000 s. `tools/post.py` has `GAMMA, SAT = 0.73, 0.88`, grain 0.005, no `-shortest`, and `+faststart`. The run took about 35 minutes or less (about 2.2 s/frame from the log; the old 4.41 s/frame figure was wrong). The user has watched it only as it opened. The user has not yet given notes.
- Git: repo `stitches-blender-remake` on GitHub holds only code and docs (`.gitignore` is a whitelist). Frames, videos, scene, audio, and the reference video stay local.

| Mean per frame | Reference | Version 1 | Version 2 |
|---|---|---|---|
| Brightness | 132.4 | 108.4 | 129.1 |
| Contrast | 52.8 | 56.6 | 52.3 |
| Saturation | 108.4 | 142.0 | 112.9 |
| Sideways motion (px/frame at 256 px wide) | 0.447 | 4.750 raw | 0.624 |
| Zoom jerk RMS | about 0.0014 | 0.001561 | 0.001463 |

Sideways motion: the second 25 row reads 6.024 in version 2. That is the fast pull-out, where phase correlation fails (frames 745-794 show a largest frame-to-frame change of 8.4, median 6.5). With a typical row in its place the mean is about 0.44 (arithmetic, not tested). Full output: `build/measure.txt` (reference and version 1), `build/measure_v2.txt` (reference and version 2). Both are local only.

## Next task
**Wait for the user's notes on picture and sound of version 2.** Nobody has listened to the sound.
- Colour, mix, or encode change: edit `tools/post.py` or `tools/mix.py`. No new render. Run `post.py` about 35 minutes. `post.py` cannot resume; a stop restarts at frame 1, and a stopped run leaves a partial MP4 with the final name.
- Shoe, hair, or calf change: rebuild the scene and render again (see the known gaps below).
- The full story is in `DEVELOPMENT-JOURNEY.html`.

If the user asks for something else, that takes precedence.

## Known gaps in the picture
- The shoe is a shell of the foot: boxier than the reference, with simple laces.
- Hair stops at z=0.505 m (no hair on the knee), and only the near lower leg has real hair.
- The calf is less bulged than the reference at the wide shots.
- A geometry fix needs a rebuild and a new render: about 5.4 hours estimated at 48 spp (first 456 frames averaged 18.8 s).

## Facts that cost time
- Claude Code stopped the render once for low memory at frame 456. `tools/render_frames.py` skips finished PNGs, so a restart resumes. `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1` at Claude Code start turns this stop off.
- A Blender relative output path went to the C: drive root. `tools/render_frames.py` now uses an absolute path.
- Another Blender job (a script from another project) ran at the same time and frame time rose from about 22 s to 36-46 s. Do not touch other jobs.
- Particle hair came out about 10 cm long and took 37 s of a 38 s test frame. Use the curves in `add_hair`.
- Default camera clip_start 0.1 m cut the leg open at the 0.105 m macro distance. It is now 0.005 m.
- `hide_render` on an empty parent does not hide its children.
- cv2 seeking on this AV1 file lands on wrong frames. Decode in order, or use ffmpeg `select`.
- `tools/measure.py` zoom under-reads the push-in by about a power of 2. `DIST` in `build_scene.py` is calibrated on stitch spacing.
- Reference loudness measures -12.0 LUFS. The transcript says about -5. Use the measured value.
- Multi-line Python heredocs with triple quotes failed in the Bash tool twice. Write a file, then run it.

## ElevenLabs
Spent: 8,843 credits, about $1.47 (voice 842, music 7,200, effects 802). Every asset in use is saved in `audio/`. Do not generate again without a reason, because each call charges.

## Workflow provenance
- Used: `blender-headless`, `handoff-after-clear`. Advisor consulted once before the build.
- Omi's paid skill was not used. The method comes from `transcript.txt`.
- Not done, by scope: the Splinters short in `README.txt`. The user asked for the stitch video only.

## Session-transient scratch
`calib.py` in the session scratchpad found the grade: grid search on GAMMA 0.55-1.00 and SAT 0.55-1.00, step 0.03, at 256x456, on frames 1, 32, 63... The result is saved in `tools/post.py`, so nothing needs regenerating. Rebuild the search from this pattern only if `grade()` changes.
