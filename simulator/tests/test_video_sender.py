"""Preserve the upstream standalone HEVC sender's wire format and local import."""

import contextlib
import io
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from simulator.tools import video_sender


class VideoSenderTest(unittest.TestCase):
    def test_direct_script_import_works_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, str(Path(video_sender.__file__).resolve())],
                cwd=temporary, capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(1, result.returncode)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_hevc_datagrams_keep_big_endian_header_and_slices(self):
        payload = bytes(range(256)) * 12
        extractor = Mock()
        extractor.push.return_value = [payload]
        extractor.flush.return_value = []
        process = Mock()
        process.stdout = io.BytesIO(b"encoded source")
        transport = Mock()
        with (
            patch.object(video_sender, "HevcAnnexBFrameExtractor", return_value=extractor),
            patch.object(video_sender.subprocess, "Popen", return_value=process),
            patch.object(video_sender.socket, "socket", return_value=transport),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            video_sender.send_video_as_hevc_udp("sample.mp4", "127.0.0.1", 3334, loop=False)
        packets = [call.args[0] for call in transport.sendto.call_args_list]
        self.assertEqual(3, len(packets))
        self.assertEqual(payload, b"".join(packet[8:] for packet in packets))
        for index, packet in enumerate(packets):
            self.assertEqual((0, index, len(payload)), struct.unpack(">HHI", packet[:8]))
            self.assertLessEqual(len(packet), video_sender.MTU_SIZE + 8)
        transport.close.assert_called_once()
        process.terminate.assert_called_once()
        self.assertTrue(process.stdout.closed)

    def test_missing_ffmpeg_releases_udp_socket(self):
        transport = Mock()
        with (
            patch.object(video_sender.socket, "socket", return_value=transport),
            patch.object(video_sender.subprocess, "Popen", side_effect=FileNotFoundError("ffmpeg")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(FileNotFoundError):
                video_sender.send_video_as_hevc_udp("sample.mp4", "127.0.0.1", 3334)
        transport.close.assert_called_once()
