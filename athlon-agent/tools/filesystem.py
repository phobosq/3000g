from pathlib import Path
from agents import function_tool
from .common import safe_path


@function_tool
def list_files(relative_path: str = ".") -> str:
    """
    List files and directories inside the project workspace.

    Args:
        relative_path: Path relative to the project root.
    """
    path = safe_path(relative_path)

    if not path.exists():
        return f"Path does not exist: {relative_path}"

    if not path.is_dir():
        return f"Not a directory: {relative_path}"

    items = []

    for item in sorted(path.iterdir()):
        kind = "DIR " if item.is_dir() else "FILE"

        if item.is_file():
            size = item.stat().st_size
            items.append(f"{kind:4} {size:12}  {item.name}")
        else:
            items.append(f"{kind:4} {'':12}  {item.name}")

    return "\n".join(items)


@function_tool
def read_text_file(relative_path: str) -> str:
    """
    Read a text file inside the project workspace.

    Args:
        relative_path: Path relative to project root.
    """
    path = safe_path(relative_path)

    if not path.exists():
        return f"File does not exist: {relative_path}"

    if not path.is_file():
        return f"Not a file: {relative_path}"

    if path.stat().st_size > 4 * 1024 * 1024:
        return "File too large for read_text_file"

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )