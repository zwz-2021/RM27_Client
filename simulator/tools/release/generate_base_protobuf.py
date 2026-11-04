"""Generate/check the shared step-1 schema; leave the legacy pb2 untouched."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

GENERATOR_VERSION = "libprotoc 29.3"


def generate(repo_root: Path, protoc: str, *, check: bool = False) -> Path:
    canonical = repo_root / "libs/protocol/proto/rm27_base.proto"
    target = repo_root / "simulator/protocol/rm27_base_pb2.py"
    if not canonical.is_file():
        raise RuntimeError("基础 schema 生成需要完整源码仓库中的 libs/protocol/proto/rm27_base.proto")
    version = subprocess.run([protoc, "--version"], check=True, capture_output=True, text=True).stdout.strip()
    if version != GENERATOR_VERSION:
        raise RuntimeError(f"基础代码固定使用 {GENERATOR_VERSION}；当前为 {version}，未修改生成文件")
    with tempfile.TemporaryDirectory(prefix="rm27-base-protobuf-") as directory:
        subprocess.run([protoc, f"--proto_path={canonical.parent}",
                        f"--python_out={directory}", str(canonical)], check=True)
        candidate = Path(directory) / target.name
        if check:
            if not target.is_file() or candidate.read_bytes() != target.read_bytes():
                raise RuntimeError("rm27_base_pb2.py 与共享 schema 不一致，请重新生成")
        else:
            shutil.copyfile(candidate, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--protoc", default=shutil.which("protoc"))
    parser.add_argument("--check", action="store_true", help="只检查生成漂移，不写文件")
    args = parser.parse_args()
    try:
        if not args.protoc:
            raise RuntimeError("找不到 protoc 29.3，请通过 --protoc 指定")
        target = generate(args.repo_root.resolve(), args.protoc, check=args.check)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"RM27 基础 Protobuf 检查失败：{error}")
        return 1
    print(f"RM27 基础 Protobuf {'漂移检查通过' if args.check else '已生成'}：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
