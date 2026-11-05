"""Mix voice, music, and effects to audio/mix.wav at the reference loudness (-12.0 LUFS). Run: python tools/mix.py"""
import subprocess

DUR = 31.031
# (source start, source end, place at) in seconds: voice take A, cut at its measured silences.
VOICE = [(0, 6.94, 0.1), (7.63, 13.72, 7.6), (14.27, 16.85, 14.3), (17.37, 21.02, 18.3), (21.59, 23.63, 24.5),
         (24.18, 27.17, 27.5)]
# (file, gain dB, trim length s, times) ; one stitch lands per 7.5 frames, as in build_scene.py STITCH_TIMES.
STITCHES = [t for t in (-0.5 + i * 7.5 / 30 + 7 / 30 for i in range(12)) if t > 0]
FX = [("audio/sfx/needle.mp3", -20, 0.45, STITCHES),
      ("audio/sfx/snip.mp3", -8, 0.5, [5.80]),
      ("audio/sfx/whoosh.mp3", -14, 2.0, [13.6, 24.7]),
      ("audio/sfx/tissue.mp3", -22, 2.0, [15.0, 17.0, 19.0, 21.0, 23.0])]

inputs, chains, labels = ["-i", "audio/voice_a.mp3", "-i", "audio/music_a.mp3"], [], []
n = 0
for a, b, at in VOICE:
    chains.append(f"[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={b - a - 0.04}:d=0.04,"
                  f"adelay={int(at * 1000)}:all=1[v{n}]")
    labels.append(f"[v{n}]")
    n += 1
chains.append(f"[1:a]volume=-15dB,atrim=0:{DUR},afade=t=out:st={DUR - 1.5}:d=1.5[m]")
labels.append("[m]")
idx = 2
for path, gain, length, times in FX:
    inputs += ["-i", path]
    for k, t in enumerate(times):
        # Drop lead-in silence so each effect lands on its time.
        chains.append(f"[{idx}:a]silenceremove=start_periods=1:start_threshold=-40dB,atrim=0:{length},asetpts=PTS-STARTPTS,"
                      f"afade=t=out:st={max(0, length - 0.08)}:d=0.08,volume={gain}dB,adelay={int(t * 1000)}:all=1[f{n}]")
        labels.append(f"[f{n}]")
        n += 1
    idx += 1
chains.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,atrim=0:{DUR},"
              "acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=4dB,"
              "loudnorm=I=-12:LRA=4:TP=-1,volume=1.9dB,alimiter=limit=0.9:level=disabled,aresample=48000[out]")
subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(chains), "-map", "[out]",
                "audio/mix.wav"], check=True)
print("OK audio/mix.wav")
