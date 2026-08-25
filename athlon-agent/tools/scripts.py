from pathlib import Path
import subprocess
import sys

from agents import function_tool


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


@function_tool
def run_project_script(
    script_name: str,
    arguments: list[str],
) -> str:
    """
    Run an approved Python script located in scripts/.

    Args:
        script_name: Script filename, for example analyze_ahci.py.
        arguments: Command-line arguments passed to the script.
    """

    script = (SCRIPTS / script_name).resolve()

    if SCRIPTS.resolve() not in script.parents:
        raise ValueError("Invalid script path")

    if not script.is_file():
        return f"Script not found: {script_name}"

    if script.suffix.lower() != ".py":
        return "Only Python scripts are allowed"

    proc = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    return (
        f"exit_code={proc.returncode}\n\n"
        f"STDOUT:\n{proc.stdout}\n\n"
        f"STDERR:\n{proc.stderr}"
    )