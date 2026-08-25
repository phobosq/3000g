from pathlib import Path
import hashlib

from agents import function_tool
from .common import safe_path

@function_tool
def file_info(relative_path: str) -> str:
    """
    Return size and SHA256 hash for a project file.

    Args:
        relative_path: File relative to project root.
    """
    path = safe_path(relative_path)

    if not path.is_file():
        return f"Not a file: {relative_path}"

    data = path.read_bytes()

    return (
        f"path={relative_path}\n"
        f"size={len(data)}\n"
        f"sha256={hashlib.sha256(data).hexdigest()}"
    )


@function_tool
def read_binary_range(
    relative_path: str,
    offset: int,
    length: int,
) -> str:
    """
    Read a binary range and return a hexadecimal dump.

    Args:
        relative_path: File relative to project root.
        offset: File offset in decimal bytes.
        length: Number of bytes to read.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")

    if length < 1 or length > 65536:
        raise ValueError("length must be between 1 and 65536")

    path = safe_path(relative_path)

    if not path.is_file():
        return f"Not a file: {relative_path}"

    with path.open("rb") as f:
        f.seek(offset)
        data = f.read(length)

    lines = []

    for pos in range(0, len(data), 16):
        chunk = data[pos:pos + 16]

        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(
            chr(b) if 32 <= b < 127 else "."
            for b in chunk
        )

        lines.append(
            f"{offset + pos:08X}  "
            f"{hex_part:<47}  "
            f"{ascii_part}"
        )

    return "\n".join(lines)


@function_tool
def find_hex_pattern(
    relative_path: str,
    hex_pattern: str,
) -> str:
    """
    Search a binary file for an exact byte pattern.

    Args:
        relative_path: File relative to project root.
        hex_pattern: Bytes such as '48 8B 43 20 48 85 C0'.
    """
    path = safe_path(relative_path)

    pattern = bytes.fromhex(hex_pattern)
    data = path.read_bytes()

    results = []
    start = 0

    while True:
        pos = data.find(pattern, start)

        if pos == -1:
            break

        results.append(pos)
        start = pos + 1

        if len(results) >= 100:
            break

    if not results:
        return "Pattern not found"

    return "\n".join(
        f"0x{position:X}"
        for position in results
    )