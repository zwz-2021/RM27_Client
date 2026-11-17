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


def make_clip(evidence, ffmpeg, ffprobe, width, height, frame_count, source_offset=0):
    # Each display frame has a different luma pattern and distinct chroma planes.
    # The pixel oracle uses no decoder, demuxer, simulator or product code.
    clip = evidence / f"known-{height}p60.hevc"
    expected = []
    with TemporaryDirectory(prefix="rm27-hevc-source-") as directory:
        raw = Path(directory) / "source.yuv"
        with raw.open("wb") as output:
            for index in range(source_offset, source_offset + frame_count):
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


def run_probe(probe, env, evidence, name, args, expected_statuses, *, expected_exit=None):
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
            elif event["status"] == "completed_with_errors":
                check(event["diagnostic"].strip() and not event["error"] and current,
                      f"{name}: missing nonfatal decoder diagnostic or output frames")
            elif event["status"] == "completed":
                check(not event["diagnostic"] and not event["error"],
                      f"{name}: clean completion has a diagnostic: {event}")
            summaries.append(event)
            sessions.append(current)
            current = []
    check(not current, f"{name}: frames without final summary")
    check([summary["status"] for summary in summaries] == expected_statuses,
          f"{name}: unexpected session results (exit {result.returncode}), see {evidence}: {summaries}")
    if expected_exit is None:
        expected_exit = int(any(status in ("completed_with_errors", "error") for status in expected_statuses))
    check(result.returncode == expected_exit,
          f"{name}: unexpected exit code {result.returncode}")
    return sessions, summaries


def compare_frames(events, hashes, width=WIDTH, height=HEIGHT, start_index=1):
    check(len(events) == len(hashes), f"Expected {len(hashes)} output frames, got {len(events)}")
    for index, (frame, value) in enumerate(zip(events, hashes), start=start_index):
        actual = (frame["index"], frame["width"], frame["height"], frame["sha256"])
        expected = (index, width, height, value)
        check(actual == expected, f"Decoded frame order, shape or pixels differ: {actual} != {expected}")


def nal_units(data):
    # Annex B fixtures only. Retain the next start code when shortening a slice.
    starts = list(re.finditer(rb"\x00\x00(?:\x00)?\x01", data))
    return [((data[match.end()] >> 1) & 0x3f, match.end(),
             starts[i + 1].start() if i + 1 < len(starts) else len(data))
            for i, match in enumerate(starts)]


def check_recovery(probe, env, evidence, ffmpeg, ffprobe, clip, expected):
    second_dir = evidence / "second-segment"
    second_dir.mkdir()
    second, second_hashes = make_clip(second_dir, ffmpeg, ffprobe, WIDTH, HEIGHT, FRAMES,
                                      source_offset=FRAMES)
    check(len(set(expected + second_hashes)) == 2 * FRAMES, "Recovery frames need unique pixel hashes")
    first_data, second_data = clip.read_bytes(), second.read_bytes()
    for data in (first_data, second_data):
        types = [kind for kind, _, _ in nal_units(data)]
        first_picture = next(i for i, kind in enumerate(types) if kind < 32)
        check(types[:3] == [32, 33, 34] and types[first_picture] in (19, 20),
              f"Segment must start with VPS/SPS/PPS and an IDR picture: {types}")
    pictures = [unit for unit in nal_units(first_data) if unit[0] < 32]
    check(len(pictures) == FRAMES, "Fixture must have one slice per picture")
    middle = len(pictures) // 2
    kind, begin, end = pictures[middle]
    check(kind < 16 and end > begin + 3, "Expected a non-key slice with payload")
    # Preserve the two-byte NAL header and only the first slice byte. The other
    # slices of the first segment and the whole second segment remain untouched.
    damaged_end = first_data[:begin + 3]
    damaged_first = damaged_end + first_data[end:]
    joined = evidence / "damaged-then-idr.hevc"
    joined.write_bytes(damaged_first + second_data)
    tail = evidence / "ends-in-damage.hevc"
    tail.write_bytes(damaged_end)
    missing = derived_clip(ffmpeg, clip, "no-pps.hevc", "-bsf:v", "filter_units=remove_types=34")
    check([kind for kind, _, _ in nal_units(missing.read_bytes())] ==
          [kind for kind, _, _ in nal_units(first_data) if kind != 34],
          "Missing-PPS fixture must retain VPS, SPS and every slice")

    sessions, summaries = run_probe(probe, env, evidence, "recovery", [joined], ["completed_with_errors"])
    frames, = sessions
    hashes = [frame["sha256"] for frame in frames]
    check(hashes.count(second_hashes[0]) == 1, "The second segment's first picture is missing or duplicated")
    recovered = hashes.index(second_hashes[0])
    check(recovered > 0 and hashes[:recovered] != expected, "Damage must affect output after a valid prefix")
    compare_frames(frames[:1], expected[:1])
    check(not set(hashes[:recovered]).intersection(second_hashes), "Second-segment picture before its IDR")
    compare_frames(frames[recovered:], second_hashes, start_index=recovered + 1)
    stop_index = recovered + 2
    stopped, stop_summaries = run_probe(probe, env, evidence, "recovery-stop",
                                        ["--stop-after", stop_index, joined], ["stopped"], expected_exit=1)
    check(stopped[0] == frames[:stop_index] and stop_summaries[0]["diagnostic"],
          "Stopping after recovery must preserve both the decoded prefix and the observed error")
    controls, control_summaries = run_probe(probe, env, evidence, "recovery-controls", [tail, missing, second],
                                            ["completed_with_errors", "error", "completed"])
    compare_frames(controls[0][:1], expected[:1])
    compare_frames(controls[1], [])
    check("pps" in control_summaries[1]["diagnostic"].lower(), "Expected a diagnostic for the missing PPS")
    compare_frames(controls[2], second_hashes)
    return {
        "file": str(joined), "damagedVclInCodedOrder": middle + 1,
        "removedSliceBytes": end - begin - 3, "secondSegmentByteOffset": len(damaged_first),
        "firstRecoveredOutputIndex": recovered + 1, "matchedRecoveryFrames": len(second_hashes),
        "secondSegmentSourceSha256": second_hashes, "summary": summaries[0], "controls": control_summaries,
        "stoppedAfterRecovery": stop_summaries[0],
    }


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
    slice_start = next(start for kind, start, _ in nal_units(picture) if kind < 32)
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
    recovery = check_recovery(probe, env, evidence, ffmpeg, ffprobe, clip, expected)
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
        "sameStreamRecovery": recovery,
        "allDisplayOrderPixelHashesMatched": True,
    })
    print(f"PASS: {FRAMES} known 1080p60 frames including delayed B pictures, all pixel hashes in order.")
    print("PASS: invalid data, missing VPS/SPS/PPS, same-process reopen and stop after three frames.")
    print(f"PASS: same-stream recovery at output {recovery['firstRecoveredOutputIndex']}, "
          f"all {recovery['matchedRecoveryFrames']} second-segment pixel hashes in order; "
          "terminal damage and missing PPS diagnosed.")
    print(f"PASS: {LONG_FRAMES} frames at 64x64, every pixel hash through end of file.")


if __name__ == "__main__":
    main()
