#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
视频推流模拟器 (HEVC版)

@file video_streamer.py
@brief 模拟图传视频推流，将本地视频通过UDP发送给客户端
@author Fudan EGA Team
@date 2026-02-01
@copyright Copyright (c) 2026 Fudan University EGA Team (复旦大学星云 EGA 机器人战队).

功能说明:
    - 使用 FFmpeg 将视频转码为 HEVC 格式
    - 通过 UDP 3334 端口发送，遵循官方协议
    - 支持手动开始/停止推流 (不再自动启动)
    - 支持自定义视频源和上传视频

官方协议规范:
    UDP 端口: 3334
    编码格式: HEVC (H.265)
    包头格式 (8 字节):
        帧编号（2 字节，递增）
        分片序号（2 字节）
        当前帧总字节数（4 字节）
"""

import socket
import threading
import time
import os
import json
import subprocess
import queue
from pathlib import Path

from .hevc_annexb import HevcAnnexBFrameExtractor
from .video_datagrams import send_video_frame


class VideoStreamer:
    """
    HEVC 视频流推流器

    使用 FFmpeg 将视频转码为 HEVC 格式，通过 UDP 发送给客户端。
    遵循官方协议：8字节包头 + HEVC 数据
    """

    def __init__(self, target_ip="127.0.0.1", port=3334, video_dir=None):
        """
        初始化推流器
        :param target_ip: 目标 IP 地址 (客户端)
        :param port: 目标端口 (官方协议: 3334)
        :param video_dir: 视频文件目录
        """
        self.target_ip = target_ip
        self.port = port
        self.script_dir = Path(__file__).resolve().parent
        self.project_root = self.script_dir.parent
        self.video_dir = self._resolve_path(video_dir or "resources/videos")

        # 模拟器内部配置；相对视频目录以 simulator/ 为基准。
        self.config_path = self.script_dir / "config.json"
        self.video_resource_path = self._resolve_path("resources/videos")
        self._load_config()

        # 状态控制
        self.current_video = ""  # 当前视频源 (空表示未设置)
        self.is_streaming = False  # 是否正在推流
        self.running = False  # 后台线程运行标志
        self._worker = None
        self._stop_event = threading.Event()
        self.paused = False  # 暂停状态
        self.error = ""

        # FFmpeg 进程
        self.ffmpeg_process = None
        self._process_lock = threading.Lock()

        # UDP 套接字
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)

        # 帧计数器
        self.frame_id = 0
        self.frame_extractor = HevcAnnexBFrameExtractor()

        # 日志回调
        self.log_callback = None

    def _load_config(self):
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if "video_resource_path" in config:
                        self.video_resource_path = self._resolve_path(config["video_resource_path"])
                        print(f"[VideoStreamer] 已加载视频资源路径: {self.video_resource_path}")
        except Exception as e:
            print(f"[VideoStreamer] 加载配置文件失败: {e}")

    def _resolve_path(self, input_path, base_dir=None):
        """将输入路径标准化为可跨平台运行的绝对路径。"""
        if not input_path:
            return ""

        path = Path(str(input_path)).expanduser()
        if path.is_absolute():
            return str(path)

        candidates = []
        if base_dir:
            candidates.append(Path(base_dir) / path)
        candidates.append(self.project_root / path)
        candidates.append(self.script_dir / path)

        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())

        # 文件不存在时，优先返回项目根目录下的目标路径，避免依赖当前工作目录
        return str((self.project_root / path).resolve())

    def _log(self, message):
        """输出日志"""
        print(f"[VideoStreamer] {message}")
        if self.log_callback:
            self.log_callback("VideoStreamer", message, "video")

    def start(self):
        """
        启动后台线程 (但不开始推流)
        推流需要调用 start_streaming()
        """
        if self.running:
            return
        self._stop_event.clear()
        self.running = True
        self._worker = threading.Thread(target=self._stream_loop, daemon=True)
        self._worker.start()
        self._log("后台线程已启动 (等待开始推流指令)")

    def stop(self):
        """停止推流并关闭资源"""
        self.running = False
        self._stop_event.set()
        self.stop_streaming()
        if self._worker is not None and self._worker is not threading.current_thread():
            self._worker.join(timeout=2)
        if self.sock:
            self.sock.close()
        self._log("推流器已完全停止")

    def start_streaming(self):
        """开始推流 (由 Web 界面手动触发)"""
        with self._process_lock:
            if self.is_streaming:
                return True
            if not self.current_video or not os.path.isfile(self.current_video):
                self.error = "请先选择可读取的视频文件。"
                return False
            self.error = ""
            self.is_streaming = True
            self.paused = False
        self._log(f"开始推流: {self.current_video}")
        return True

    def stop_streaming(self):
        """停止推流"""
        with self._process_lock:
            self.is_streaming = False
            self.paused = False
        self._stop_ffmpeg()
        self._log("推流已停止")

    def pause(self):
        """暂停推流"""
        with self._process_lock:
            if not self.is_streaming:
                return
            self.paused = True
        self._log("推流已暂停")

    def resume(self):
        """恢复推流"""
        with self._process_lock:
            if not self.is_streaming:
                return
            self.paused = False
        self._log("推流已恢复")

    def set_video_file(self, filename):
        """
        设置视频源
        :param filename: 视频文件名或完整路径
        :return: 成功返回 True
        """
        # 尝试多个路径
        input_name = (filename or "").strip()
        paths_to_check = [
            self._resolve_path(input_name, base_dir=self.video_resource_path),
            self._resolve_path(input_name, base_dir=self.video_dir),
            self._resolve_path(input_name)  # 直接作为完整路径
        ]

        for path in paths_to_check:
            if os.path.exists(path):
                self.current_video = path
                self._log(f"视频源已设置: {path}")
                return True

        self._log(f"未找到视频文件: {filename}")
        return False

    def get_available_videos(self):
        """获取可用视频列表"""
        videos = []
        dirs = {
            self._resolve_path("resources/videos"),
            self.video_dir,
            self.video_resource_path
        }
        for d in dirs:
            if d and os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(('.mp4', '.avi', '.mov', '.mkv', '.hevc', '.h265')):
                        videos.append(f)
        return list(set(videos))

    def get_status(self):
        """获取当前状态"""
        with self._process_lock:
            return {
                "is_streaming": self.is_streaming,
                "paused": self.paused,
                "current_video": os.path.basename(self.current_video) if self.current_video else "",
                "frame_id": self.frame_id,
                "error": self.error,
            }

    def _start_ffmpeg(self):
        """启动 FFmpeg 进程进行 HEVC 转码"""
        if self.ffmpeg_process:
            self._stop_ffmpeg()

        # FFmpeg 命令: 读取视频 -> HEVC 编码 -> 输出原始 HEVC 流到 stdout
        # 增加 Annex B 格式支持 (vbsf hevc_mp4toannexb) 确保码流包含必要头信息
        cmd = [
            "ffmpeg",
            "-re",                       # 按原始帧率读取
            "-stream_loop", "-1",        # 循环播放
            # Limit frames held by the input decoder when the recording loops.
            "-threads", "2",
            "-i", self.current_video,
            "-c:v", "libx265",           # HEVC 编码
            "-preset", "ultrafast",      # 最快编码速度
            "-tune", "zerolatency",      # 零延迟
            "-x265-params", "keyint=15:min-keyint=15:scenecut=0",  # 每 15 帧一个关键帧
            "-bsf:v", "hevc_mp4toannexb", # 强制转换为 Annex B 格式 (包含 VPS/SPS/PPS)
            "-an",                       # 禁用音频
            "-flush_packets", "1",
            "-f", "hevc",                # 输出格式为原始 HEVC
            "-"                          # 输出到 stdout
        ]

        try:
            with self._process_lock:
                if not self.running or not self.is_streaming:
                    return False
                self.ffmpeg_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=10**6,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            self.frame_extractor.reset()
            self._log("FFmpeg HEVC 编码器已启动")
            return True
        except OSError as error:
            self._fail_stream(None, f"无法启动 FFmpeg，请检查安装和 PATH。{error}")
            return False

    def _fail_stream(self, process, detail):
        # 停止后重启时，旧进程的 EOF/异常不能覆盖新一轮状态。
        with self._process_lock:
            if not self.is_streaming or self.ffmpeg_process is not process:
                return
            self.is_streaming = False
            self.paused = False
            self.error = detail
        self._log(detail)
        self._stop_ffmpeg()

    def _stop_ffmpeg(self):
        """停止 FFmpeg 进程并回收 stdout。"""
        with self._process_lock:
            process = self.ffmpeg_process
            self.ffmpeg_process = None
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            finally:
                if process.stdout:
                    process.stdout.close()
            self._log("FFmpeg 进程已停止")

    def _stream_loop(self):
        """推流主循环"""
        sent_frame = False
        while self.running:
            # 等待开始推流
            if not self.is_streaming:
                self._stop_event.wait(0.1)
                continue

            # 暂停状态
            if self.paused:
                self._stop_event.wait(0.1)
                continue

            # 启动 FFmpeg (如果尚未启动)
            if not self.ffmpeg_process:
                if not self._start_ffmpeg():
                    continue
                sent_frame = False

            try:
                # 读取连续 HEVC Annex-B 码流，并提取访问单元后发送
                process = self.ffmpeg_process
                if process is None:
                    continue
                # A low-bitrate frame may be far shorter than one pipe read.
                data = process.stdout.read1(64 * 1024)
                if not self.is_streaming or self.ffmpeg_process is not process:
                    continue

                frames = self.frame_extractor.push(data) if data else self.frame_extractor.flush()
                for frame in frames:
                    if not self.is_streaming or self.ffmpeg_process is not process:
                        break
                    self._send_frame(frame)
                    sent_frame = True

                if not data:
                    code = process.wait(timeout=2)
                    if code:
                        self._fail_stream(process, f"FFmpeg 未能完成视频转码（退出码 {code}），请检查视频文件。")
                    elif not sent_frame:
                        self._fail_stream(process, "FFmpeg 没有输出视频帧，请检查视频文件。")
                    else:
                        self._stop_ffmpeg()
                    continue

            except Exception as e:
                self._fail_stream(process, f"图传发送失败：{e}")

    def _send_frame(self, data):
        frame_id = self.frame_id
        self.frame_id = (self.frame_id + 1) % 65536
        count, _ = send_video_frame(self.sock, (self.target_ip, self.port), frame_id, data)

        if frame_id % 60 == 0:
            self._log(f"已发送帧 {frame_id}, 大小 {len(data)}B, 分片 {count}")
