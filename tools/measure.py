"""Measure one video per frame. Usage: python tools/measure.py VIDEO [OTHER_VIDEO]
With two videos, also print the delta: the to-do list from the transcript's method."""
import sys
import cv2
import numpy as np


def hann(shape):
    return cv2.createHanningWindow((shape[1], shape[0]), cv2.CV_32F)


def logpolar_mag(gray, win):
    mag = np.abs(np.fft.fftshift(np.fft.fft2(gray * win))).astype(np.float32)
    mag = np.log1p(mag)
    h, w = mag.shape
    return cv2.warpPolar(mag, (w, h), (w / 2, h / 2), min(h, w) / 2,
                         cv2.WARP_POLAR_LOG | cv2.INTER_LINEAR)


def measure(path, size=(256, 456)):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    rows, prev, prev_lp, win = [], None, None, None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        if win is None:
            win = hann(gray.shape)
        lp = logpolar_mag(gray, win)
        dx = dy = 0.0
        zoom = 1.0
        if prev is not None:
            (dx, dy), _ = cv2.phaseCorrelate(prev, gray, win)
            (dr, _), _ = cv2.phaseCorrelate(prev_lp, lp)
            # log-polar x axis: r = (w / ln(maxR)) * ln(rho), after warpPolar's linear scale
            k = gray.shape[1] / np.log(min(gray.shape) / 2)
            zoom = float(np.exp(-dr / k))  # spectrum shrinks when the image zooms in
        # Background sample: top-left 8% square; blue only appears in wide shots.
        bg = small[:36, :20].reshape(-1, 3).mean(0)[::-1]
        rows.append((gray.mean() * 255, gray.std() * 255, hsv[..., 1].mean(),
                     dx, dy, zoom, *bg))
        prev, prev_lp = gray, lp
    cap.release()
    return fps, np.array(rows)


def report(name, fps, a):
    scale = np.cumprod(a[:, 5])
    lateral = np.hypot(a[:, 3], a[:, 4])
    jerk = np.diff(scale, 3)
    print(f"== {name}: {len(a)} frames at {fps:.3f} fps")
    print("sec luma contrast sat  lateral_px  zoom_cum  bgR bgG bgB")
    for s in range(0, len(a), int(round(fps))):
        i = min(s, len(a) - 1)
        j = min(s + int(round(fps)), len(a))
        print(f"{s / fps:4.0f} {a[i, 0]:5.1f} {a[i, 1]:6.1f} {a[i, 2]:5.1f} "
              f"{lateral[i:j].mean():8.3f} {scale[i]:9.3f}  "
              f"{a[i, 6]:3.0f} {a[i, 7]:3.0f} {a[i, 8]:3.0f}")
    print(f"mean luma {a[:, 0].mean():.1f}, contrast {a[:, 1].mean():.1f}, "
          f"sat {a[:, 2].mean():.1f}, lateral {lateral.mean():.3f} px/frame "
          f"(of 256 wide), zoom jerk rms {np.sqrt((jerk ** 2).mean()):.6f}")
    return dict(luma=a[:, 0].mean(), contrast=a[:, 1].mean(), sat=a[:, 2].mean(),
                lateral=lateral.mean(), jerk=np.sqrt((jerk ** 2).mean()))


if __name__ == "__main__":
    results = []
    for p in sys.argv[1:]:
        fps, a = measure(p)
        results.append(report(p, fps, a))
    if len(results) == 2:
        print("== delta (second minus first)")
        for k in results[0]:
            print(f"{k}: {results[0][k]:.4f} -> {results[1][k]:.4f}")
