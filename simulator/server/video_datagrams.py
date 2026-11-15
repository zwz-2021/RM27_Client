"""RM27 通信协议第 2 章（PDF 第 47 页）的标准图传 UDP 分片。"""

import socket
from struct import Struct


MAX_DATAGRAM_BYTES = 1400
_HEADER = Struct("!HHI")
_DATA_BYTES = MAX_DATAGRAM_BYTES - _HEADER.size


def send_video_frame(sock: socket.socket, target: tuple[str, int], frame_number: int,
                     frame: bytes) -> tuple[int, int]:
    """发送一帧，返回已发送的分片数和含头字节数。模拟器片号从 0 开始。"""
    size = len(frame)
    slice_count = (size + _DATA_BYTES - 1) // _DATA_BYTES
    if slice_count > 65536:
        raise ValueError("图传帧过大，分片序号超出 16 位范围")

    frame_id = frame_number % 65536
    for slice_id, offset in enumerate(range(0, size, _DATA_BYTES)):
        header = _HEADER.pack(frame_id, slice_id, size)
        sock.sendto(header + frame[offset:offset + _DATA_BYTES], target)

    return slice_count, size + slice_count * _HEADER.size
