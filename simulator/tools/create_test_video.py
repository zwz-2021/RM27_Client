"""Generate a local synthetic video fixture without redistributing match footage."""

import argparse
from pathlib import Path
import shutil
import subprocess


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=3)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "resources/videos/testdemo.mp4")
    args = parser.parse_args(argv)
    if not 1 <= args.duration <= 60:
        parser.error("duration must be 1..60 seconds")
    executable = shutil.which("ffmpeg")
    if executable is None:
        parser.error("FFmpeg is required; add ffmpeg to this process's PATH")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        executable, "-n", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
        "-t", str(args.duration), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an", str(output),
    ], check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
