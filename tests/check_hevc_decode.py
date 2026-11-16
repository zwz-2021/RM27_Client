"""Verify the local HEVC probe against pixels generated before lossless encoding."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FRAMES = 1920, 1080, 12
LONG_FRAMES = 1201


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def json_file(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_clip(evidence, ffmpeg, ffprobe, width, height, frame_count):
    # Each display frame has a different luma pattern and distinct chroma planes.
    # The pixel oracle uses no decoder, demuxer, simulator or product code.
    clip = evidence / f"known-{height}p60.hevc"
    expected = []
    with TemporaryDirectory(prefix="rm27-hevc-source-") as directory:
        raw = Path(directory) / "source.yuv"
        with raw.open("wb") as output:
            for index in range(frame_count):
                left = (width // 24) * (index % 23 + 1)
                row = bytes([32 + index % 160]) * left + bytes([200 - index % 160]) * (width - left)
                frame = (row * height
                         + bytes([90 + index % 100]) * (width * height // 4)
                         + bytes([160 - index % 140]) * (width * height // 4))
                output.write(frame)
                expected.append(hashlib.sha256(frame).hexdigest())
        subprocess.run([
            ffmpeg, "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "yuv420p",
            "-s:v", f"{width}x{height}", "-r", "60", "-i", str(raw), "-c:v", "libx265",
            "-preset", "ultrafast", "-x265-params",
            "lossless=1:bframes=3:b-adapt=0:keyint=60:scenecut=0:pools=2:frame-threads=1:log-level=error",
            "-f", "hevc", str(clip),
        ], check=True, timeout=60)
    metadata = json.loads(subprocess.check_output([
        ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=codec_name,width,height,r_frame_rate:frame=pict_type", "-of", "json", str(clip),
    ], timeout=30))
    json_file(evidence / "fixture.json", {"sourceSha256": expected, "ffprobe": metadata})
    stream, = metadata["streams"]
    check((stream["codec_name"], stream["width"], stream["height"], stream["r_frame_rate"])
          == ("hevc", width, height, "60/1"), stream)
    types = [frame["pict_type"] for frame in metadata["frames"]]
    check(len(types) == frame_count and "B" in types,
          f"Expected {frame_count} frames including B pictures, got {len(types)} with types {set(types)}")
    return clip, expected


def derived_clip(ffmpeg, clip, name, *options):
    derived = clip.with_name(name)
    subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(clip), "-c:v", "copy",
                    *options, "-f", "hevc", str(derived)], check=True, timeout=30)
    check(derived.stat().st_size > 0, f"Empty test fixture {derived}")
    return derived


def run_probe(probe, env, evidence, name, args, expected_statuses):
    result = subprocess.run([str(probe), *map(str, args)], capture_output=True, env=env, timeout=45)
    (evidence / f"{name}.jsonl").write_bytes(result.stdout)
    (evidence / f"{name}.stderr.log").write_bytes(result.stderr)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    summaries, sessions, current = [], [], []
    for event in events:
        if event["event"] == "frame":
            current.append(event)
        else:
            check(event["event"] == "summary", f"{name}: unexpected event {event}")
            check(event["frames"] == len(current), f"{name}: summary count differs from frame events")
            if event["status"] == "error":
                check(event["error"].strip(), f"{name}: missing error detail")
            summaries.append(event)
            sessions.append(current)
            current = []
    check(not current, f"{name}: frames without final summary")
    check([summary["status"] for summary in summaries] == expected_statuses,
          f"{name}: unexpected session results (exit {result.returncode}), see {evidence}: {summaries}")
    check((result.returncode != 0) == ("error" in expected_statuses),
          f"{name}: unexpected exit code {result.returncode}")
    return sessions, summaries


def compare_frames(events, hashes, width=WIDTH, height=HEIGHT):
    check(len(events) == len(hashes), f"Expected {len(hashes)} output frames, got {len(events)}")
    for index, (frame, value) in enumerate(zip(events, hashes), start=1):
        actual = (frame["index"], frame["width"], frame["height"], frame["sha256"])
        expected = (index, width, height, value)
        check(actual == expected, f"Decoded frame order, shape or pixels differ: {actual} != {expected}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--probe", type=Path, help="Use this executable with the current runtime PATH")
    parser.add_argument("--ffmpeg", type=Path, help="Fixture encoder and decoder executable")
    parser.add_argument("--ffprobe", type=Path, help="Fixture inspection executable")
    args = parser.parse_args()
    env = os.environ.copy()
    if args.probe:
        probe = args.probe.resolve(strict=True)
    else:
        preset = "local-" + args.configuration.lower()
        probe = (ROOT / "build" / preset / "bin" / "RM27_HevcDecodeProbe.exe").resolve(strict=True)
        presets = json.loads((ROOT / "CMakeUserPresets.json").read_text(encoding="utf-8-sig"))
        paths = next(item["environment"] for item in presets["configurePresets"] if item["name"] == preset)
        env["PATH"] = os.pathsep.join((str(Path(paths["RM27_QT_ROOT"]) / "bin"),
                                       str(Path(paths["RM27_MINGW_ROOT"]) / "bin"), env["PATH"]))
    ffmpeg = args.ffmpeg.resolve(strict=True) if args.ffmpeg else "ffmpeg"
    ffprobe = args.ffprobe.resolve(strict=True) if args.ffprobe else "ffprobe"
    if args.ffmpeg:
        # The product probe resolves its FFmpeg subprocess through its own PATH.
        env["PATH"] = str(ffmpeg.parent) + os.pathsep + env["PATH"]

    evidence = ROOT / "logs" / datetime.now().strftime("check-hevc-%Y%m%d-%H%M%S-%f")
    evidence.mkdir(parents=True)
    print(f"Evidence: {evidence}", flush=True)
    clip, expected = make_clip(evidence, ffmpeg, ffprobe, WIDTH, HEIGHT, FRAMES)
    first = derived_clip(ffmpeg, clip, "first-picture.hevc", "-frames:v", "1")
    missing = derived_clip(ffmpeg, clip, "no-parameter-sets.hevc", "-bsf:v", "filter_units=remove_types=32-34")
    # Keep the genuine parameter sets, two-byte NAL header and just one slice byte.
    picture = first.read_bytes()
    headers = (m.end() for m in re.finditer(rb"\x00\x00(?:\x00)?\x01", picture))
    slice_start = next(pos for pos in headers if ((picture[pos] >> 1) & 0x3f) < 32)
    bad = evidence / "truncated-slice.hevc"
    bad.write_bytes(picture[:slice_start + 3])

    valid, valid_summary = run_probe(probe, env, evidence, "complete", [clip], ["completed"])
    compare_frames(valid[0], expected)
    mixed, mixed_summary = run_probe(probe, env, evidence, "reopen", [clip, bad, missing, clip],
                                     ["completed", "error", "error", "completed"])
    for session, hashes in zip(mixed, (expected, [], [], expected)):
        compare_frames(session, hashes)
    stopped, stopped_summary = run_probe(probe, env, evidence, "stop", ["--stop-after", 3, clip, first],
                                         ["stopped", "completed"])
    compare_frames(stopped[0], expected[:3])
    compare_frames(stopped[1], expected[:1])
    # Cover long streams and end-of-file without repeatedly encoding a full-size match clip.
    long_run = evidence / "many-frames"
    long_run.mkdir()
    long_clip, long_hashes = make_clip(long_run, ffmpeg, ffprobe, 64, 64, LONG_FRAMES)
    sequence, long_summary = run_probe(probe, env, long_run, "complete", [long_clip], ["completed"])
    compare_frames(sequence[0], long_hashes, width=64, height=64)
    json_file(evidence / "summary.json", {
        "probe": str(probe), "ffmpeg": subprocess.check_output([ffmpeg, "-version"]).splitlines()[0].decode(),
        "knownFrames": FRAMES, "width": WIDTH, "height": HEIGHT, "frameRate": "60/1",
        "complete": valid_summary, "reopen": mixed_summary, "stop": stopped_summary, "manyFrames": long_summary,
        "allDisplayOrderPixelHashesMatched": True,
    })
    print(f"PASS: {FRAMES} known 1080p60 frames including delayed B pictures, all pixel hashes in order.")
    print("PASS: invalid data, missing VPS/SPS/PPS, same-process reopen and stop after three frames.")
    print(f"PASS: {LONG_FRAMES} frames at 64x64, every pixel hash through end of file.")


if __name__ == "__main__":
    main()
