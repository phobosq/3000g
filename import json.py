import json
from pathlib import Path
from datetime import datetime

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_dirs(base):
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "prompts").mkdir(parents=True, exist_ok=True)
    (base / "responses").mkdir(parents=True, exist_ok=True)

def build_dossier(config, cycle_no):
    board = config["board"]
    bios = config["bios"]
    cpu = config["cpu"]
    post = config["post"]
    last_change = config["last_change"]
    known_good = config["known_good"]
    assumptions = config["assumptions"]

    text = f"""
# BIOS Investigation Dossier
Cycle: {cycle_no}
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## System
- Board: {board}
- BIOS: {bios}
- Target CPU: {cpu}

## Current state
- POST symptoms: {post}
- Last change: {last_change}
- Known-good state: {known_good}

## Assumptions
- {chr(10).join(f'- {a}' for a in assumptions)}

## Objective
Propose the next most likely BIOS modification to enable target CPU initialization without unrelated changes.

## Investigation targets
- CPU support gate
- AGESA / microcode compatibility
- board ID or SKU mismatch
- memory training / init blocker
- PCIe or power sequencing issue
"""
    return text

def build_prompt_for_chatgpt(config, dossier_text):
    return f"""
You are the main BIOS patch author.

Mission:
Propose the next BIOS modification to enable the target CPU to initialize on this board.

Use the dossier below as your source of truth.

Dossier:
{dossier_text}

Constraints:
- Keep patch scope narrow.
- Explain the likely BIOS area.
- Explain why this is the most plausible next step.
- State expected POST progression if correct.
- State what would invalidate the hypothesis.
- If uncertain, say so clearly.

Return format:
1. Hypothesis
2. Likely BIOS area
3. Candidate edit
4. Why this is plausible
5. Expected symptom change
6. What would falsify this
"""

def build_prompt_for_claude(config, patch_text):
    return f"""
You are the independent BIOS reviewer.

Review the proposal below critically. Do not assume it is correct.

Proposal:
{patch_text}

Focus on:
- wrong CPU family assumptions
- AGESA / microcode mismatch
- hidden side effects
- missing validation
- alternative causes
- overbroad change
- incorrect POST interpretation

Return format:
1. Major concerns
2. Missing evidence
3. Alternative hypotheses
4. Safer alternative edits
5. Minimal validation plan
"""

def main():
    base = Path(".")
    ensure_dirs(base)

    config = load_config(base / "bios_config.json")
    cycle_no = config.get("cycle_no", 1)

    dossier = build_dossier(config, cycle_no)
    (base / "dossier.md").write_text(dossier, encoding="utf-8")

    gp = build_prompt_for_chatgpt(config, dossier)
    (base / "prompts" / "chatgpt_prompt.txt").write_text(gp, encoding="utf-8")

    claude_in = build_prompt_for_claude(config, "PASTE CHATGPT RESPONSE HERE")
    (base / "prompts" / "claude_prompt.txt").write_text(claude_in, encoding="utf-8")

    decision = """
# Decision Log
- Status: pending
- Accept / Reject / Retry: pending
- Hardware test required: yes
- Next action: wait for ChatGPT response and Claude review
"""
    (base / "logs" / f"cycle_{cycle_no}.md").write_text(decision, encoding="utf-8")
    print("BIOS investigation scaffold created.")

if __name__ == "__main__":
    main()