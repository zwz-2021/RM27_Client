#!/usr/bin/env python3
"""从 canonical schema 重新生成模拟器 Python Protobuf 代码。"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Sequence

if __package__:
    from .check_sim_protobuf_runtime import parse_generated_runtime, RuntimeContractError
else:
    from check_sim_protobuf_runtime import parse_generated_runtime, RuntimeContractError


class GenerationError(RuntimeError):
    """表示生成环境或 protoc 执行结果不满足要求。"""


def build_command(project_root: Path, protoc: str) -> list[str]:
    proto_root = project_root / "protocol"
    canonical = proto_root / "robomaster.proto"
    output_dir = project_root
    if not canonical.is_file():
        raise GenerationError("缺少 protocol/robomaster.proto")
    if not output_dir.is_dir():
        raise GenerationError("缺少 simulator 项目目录")
    return [
        protoc,
        f"--proto_path={proto_root}",
        f"--python_out={output_dir}",
        str(canonical),
    ]


def generate(project_root: Path, *, protoc: str | None = None) -> Path:
    executable = protoc or shutil.which("protoc")
    if not executable:
        raise GenerationError("找不到 protoc，请先安装 Protobuf 编译器")

    command = build_command(project_root, executable)
    generated = project_root / "robomaster_pb2.py"
    if not generated.is_file():
        raise GenerationError("缺少上游 robomaster_pb2.py，无法确认生成版本契约")
    try:
        expected = parse_generated_runtime(generated)
    except RuntimeContractError as error:
        raise GenerationError(str(error)) from error

    # Generate away from the checked-in file. Older protoc must never silently
    # replace the preserved 6.33.2 Python output with an incompatible generator.
    with tempfile.TemporaryDirectory(prefix="rm27-protobuf-generate-") as temporary:
        output_dir = Path(temporary)
        command = [f"--python_out={output_dir}" if item.startswith("--python_out=") else item
                   for item in command]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise GenerationError(f"protoc 执行失败：{details or completed.returncode}")
        candidate = output_dir / "robomaster_pb2.py"
        if not candidate.is_file():
            raise GenerationError("protoc 未生成 robomaster_pb2.py")
        try:
            actual = parse_generated_runtime(candidate)
        except RuntimeContractError as error:
            raise GenerationError(str(error)) from error
        if actual != expected:
            raise GenerationError(
                f"生成器版本 {actual} 与保留的 {expected} 不一致；原 pb2 未修改。"
                "请使用匹配的 protoc，或先明确升级依赖和协议生成契约。"
            )
        shutil.copyfile(candidate, generated)

    return generated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 protocol/robomaster.proto 生成模拟器 pb2"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="独立 simulator 项目根目录，默认由脚本位置推导",
    )
    parser.add_argument("--protoc", help="protoc 可执行文件，默认从 PATH 查找")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        generated = generate(args.project_root.resolve(), protoc=args.protoc)
    except GenerationError as error:
        print(f"模拟器 Protobuf 生成失败：{error}")
        return 1
    print(f"模拟器 Protobuf 已生成：{generated.relative_to(args.project_root.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
