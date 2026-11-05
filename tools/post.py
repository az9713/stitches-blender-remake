"""Finish rendered RGBA frames: colour grade, measured blue gradient, glow, soft lens, vignette, grain, upscale to 1296x2304.
Usage:
  python tools/post.py sheet FRAME_DIR OUT.png F [F...]    side-by-side with the reference at each frame
  python tools/post.py video FRAME_DIR OUT.mp4 [AUDIO]     whole film at 30000/1001 fps
Works on display-referred values: the blue comes out exactly as measured, whatever the view transform did."""
import glob
import os
import subprocess
import sys
import cv2
import numpy as np

W, H = 1296, 2304
REF = "reference/stitches/ttuKeS5k4Uo.mp4"
YS = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1]
# RGB down the frame's left edge, measured on the reference at t=0 and t=30 s.
G0 = np.array([(89, 187, 255), (108, 197, 255), (133, 208, 255), (149, 217, 255), (160, 222, 255), (174, 222, 255),
               (173, 227, 255), (173, 227, 255), (169, 224, 255), (158, 217, 255), (145, 209, 255)], float)
G30 = np.array([(63, 171, 255), (76, 177, 255), (100, 188, 255), (116, 197, 255), (136, 207, 255), (147, 211, 255),
                (151, 215, 255), (153, 214, 255), (150, 210, 255), (143, 206, 255), (140, 204, 255)], float)
# Grade on the foreground only. Grid search on 30 sampled frames (every 31st) against the reference on measure.py's
# metrics. finish() then gives luma 130.9 / contrast 52.5 / sat 110.5; reference 132.5 / 52.8 / 108.1.
GAMMA, SAT = 0.73, 0.88
GRAIN = 0.005
RNG = np.random.default_rng(1)
YY, XX = np.mgrid[0:H, 0:W]
VIGNETTE = (1 - 0.18 * np.clip(np.hypot((XX - W / 2) / (W / 2), (YY - H / 2) / (H / 2)) - 0.55, 0, 1) ** 2)[..., None].astype(np.float32)
del YY, XX


def gradient(frame):
    k = np.clip((frame - 1) / 800, 0, 1)
    g = G0 * (1 - k) + G30 * k
    y = np.linspace(0, 1, H)
    col = np.stack([np.interp(y, YS, g[:, c]) for c in range(3)], 1)  # RGB
    return np.repeat(col[:, None, :], W, 1)[..., ::-1].astype(np.float32) / 255  # BGR float


def grade(bgr, gamma, sat):
    bgr = np.power(np.clip(bgr, 0, 1), gamma)
    luma = (bgr * np.array([0.114, 0.587, 0.299], np.float32)).sum(2, keepdims=True)
    return np.clip(luma + sat * (bgr - luma), 0, 1)


# ponytail: vignette, glow, grain are values tuned by eye against the reference; measure.py checks the result.
def finish(path, frame):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED).astype(np.float32) / 255
    im = cv2.resize(im, (W, H), interpolation=cv2.INTER_LANCZOS4)
    a = np.clip(im[..., 3:], 0, 1)
    out = grade(im[..., :3], GAMMA, SAT) * a + gradient(frame) * (1 - a)  # Blender PNG is straight alpha
    out = cv2.GaussianBlur(out, (0, 0), 0.9)  # softer lens
    glow = cv2.GaussianBlur(np.clip(out - 0.75, 0, 1), (0, 0), 28)
    out = (out + glow * 0.7) * VIGNETTE
    out += RNG.normal(0, GRAIN, (H, W, 1)).astype(np.float32)
    return np.clip(out * 255, 0, 255).astype(np.uint8)


def sheet(frames_dir, out_path, frames):
    cap = cv2.VideoCapture(REF)  # decode in order: cv2 seeking on this AV1 file lands on wrong frames
    refs, n = {}, 0
    while n < max(frames):
        ok, img = cap.read()
        n += 1
        if n in frames:
            refs[n] = img
    rows = []
    for f in frames:
        pair = np.hstack((cv2.resize(refs[f], (W // 3, H // 3)),
                          cv2.resize(finish(f"{frames_dir}/f{f:04d}.png", f), (W // 3, H // 3))))
        rows.append(pair)
    cols = min(4, len(rows))
    while len(rows) % cols:
        rows.append(np.zeros_like(rows[0]))
    cv2.imwrite(out_path, np.vstack([np.hstack(rows[i:i + cols]) for i in range(0, len(rows), cols)]))


def video(frames_dir, out_path, audio):
    files = sorted(glob.glob(f"{frames_dir}/f*.png"))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", "30000/1001",
           "-i", "-"] + (["-i", audio] if audio else []) + ["-c:v", "libx264", "-crf", "20", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart"] + (["-c:a", "aac", "-b:a", "256k"] if audio else []) + [out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i, path in enumerate(files):
        p.stdin.write(finish(path, int(os.path.basename(path)[1:5])).tobytes())
        if i % 50 == 0:
            print("frame", i, flush=True)
    p.stdin.close()
    p.wait()
    print("OK", out_path, len(files), "frames")


if __name__ == "__main__":
    mode, d, o, *rest = sys.argv[1:]
    if mode == "sheet":
        sheet(d, o, [int(x) for x in rest])
    else:
        video(d, o, rest[0] if rest else None)
