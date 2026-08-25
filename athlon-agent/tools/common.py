from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def safe_path(relative_path: str) -> Path:
    """
    Resolve a project-relative path and reject access outside
    the athlon-agent workspace.
    """

    path = (ROOT / relative_path).resolve()
    root = ROOT.resolve()

    if path != root and root not in path.parents:
        raise ValueError(
            f"Access outside project directory denied: {relative_path}"
        )

    return path