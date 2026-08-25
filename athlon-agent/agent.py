import sys
from pathlib import Path

from dotenv import load_dotenv

from agents import (
    Agent,
    Runner,
    ModelSettings,
)

from tools import ALL_TOOLS


ROOT = Path(__file__).resolve().parent


def load_file(name: str) -> str:
    return (ROOT / name).read_text(
        encoding="utf-8",
        errors="replace",
    )


load_dotenv(ROOT / ".env")


base_instructions = load_file("instructions.md")
project_state = load_file("project_state.md")


instructions = f"""
{base_instructions}


============================================================
CURRENT PROJECT STATE
============================================================

{project_state}

============================================================

Treat CURRENT PROJECT STATE as the authoritative current
state of this specific project.

Older evidence must not override newer experiments.
"""


agent = Agent(
    name="Athlon 3000G X570 BIOS Agent",

    model="gpt-5.6-sol",

    instructions=instructions,

    tools=ALL_TOOLS,

    model_settings=ModelSettings(
        reasoning={
            "effort": "high",
        },
    ),
)


def main():
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = input("athlon> ")

    result = Runner.run_sync(
        agent,
        request,
    )

    print()
    print("=" * 72)
    print(result.final_output)
    print("=" * 72)


if __name__ == "__main__":
    main()