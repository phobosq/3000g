import json
from pathlib import Path
from datetime import datetime

BASE = Path(r"c:\temp\3000g")
CONFIG_PATH = BASE / "bios_config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_dirs():
    (BASE / "cycle_234").mkdir(exist_ok=True, parents=True)
    (BASE / "prompts").mkdir(exist_ok=True, parents=True)
    (BASE / "logs").mkdir(exist_ok=True, parents=True)

def write_dossier(cfg):
    text = f"""# BIOS Investigation Dossier — Cycle {cfg['cycle_no']}

## Project
- Board: {cfg['board']['manufacturer']} {cfg['board']['model']}
- BIOS target: {cfg['board']['bios_target_version']}
- CPU target: {cfg['cpu']['name']} ({cfg['cpu']['architecture']}, Family {cfg['cpu']['family']}, Model {cfg['cpu']['model']})
- Status date: {cfg['status_date']}

## Objective
{cfg['objective']['summary']}

## Current blocker
{cfg['current_state']['current_blocker']}

## Current path
{cfg['current_state']['current_path']}

## Known facts
- V86/V87 is the active baseline.
- SataController is no longer the primary blocker.
- AHCI dispatch is functional after forced DXE ordering.
- The value assembled from +0x108/+0x10C is non-zero.
- The initial RBX == 0 theory is invalid.
- The error is deeper inside 0x65FC.

## Working hypothesis
{cfg['working_hypothesis']['summary']}

## Next actions
{chr(10).join(f'- {step}' for step in cfg['next_actions'])}

## Validated progress
{chr(10).join(f'- {item['version']}: {item['result']} => {item['meaning']}' for item in cfg['validated_progress'])}

## Candidate next build
- Next version hint: {cfg['candidate_build']['next_version_hint']}
- Expected behavior: {cfg['candidate_build']['expected_behavior']}
"""
    out = BASE / "cycle_234" / "cycle_234_dossier.md"
    out.write_text(text, encoding="utf-8")

def write_chatgpt_prompt():
    prompt = """You are the main BIOS patch author for a BIOS compatibility project.

Mission:
Propose the next BIOS modification to move the target CPU support path forward.

Use this dossier as the current source of truth.

Project:
- Board: ASRock X570 Taichi
- BIOS target: 2.70
- CPU target: Athlon 3000G (Raven Ridge / Family 17h Model 11h)
- Cycle: 234

Current status:
- SataController is OK
- AHCI dispatch is enabled
- AHCI Start() reaches helper 0x2078
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST code: 07
- value from +0x108/+0x10C is non-zero
- initial RBX == 0 theory is invalid

Constraints:
- Keep scope narrow.
- Do not go back to generic Apriori / DEPEX changes unless necessary.
- Focus on the next likely branch inside 0x65FC.
- Explain the likely cause in terms of a basic block, call, test, or compare that still leads to EFI_DEVICE_ERROR.
- Explain why this is more plausible than earlier hypotheses.
- State what would invalidate the hypothesis.
- State expected symptoms if this is correct.
- Keep output technical and evidence-based.

Return format:
1. Hypothesis
2. Most likely BIOS area / function
3. Candidate edit or instrumentation
4. Why this is plausible
5. Expected POST behavior if correct
6. What would falsify this
7. Minimal next validation steps
"""
    (BASE / "prompts" / "chatgpt_prompt_234.txt").write_text(prompt, encoding="utf-8")

def write_claude_prompt():
    prompt = """You are the independent BIOS reviewer for a CPU compatibility project.

Review the proposed BIOS change / diagnosis below critically.

Focus on:
- false assumptions
- branch misidentification
- hidden side effects
- alternate root causes
- missing validation
- the possibility that the error is still inside the same helper but on a later basic block
- risk of overbroad change

Current evidence:
- SataController OK
- AHCI dispatch OK
- AHCI Start() enters helper 0x2078
- helper 0x2078 enters helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value at +0x108/+0x10C is non-zero
- initial RBX == 0 theory is false

Return format:
1. Major concerns
2. Missing evidence
3. Alternative hypotheses
4. Safer alternative edits or instrumentation
5. Minimal validation plan before next flash
6. Final verdict: accept / reject / need more evidence
"""
    (BASE / "prompts" / "claude_prompt_234.txt").write_text(prompt, encoding="utf-8")

def write_decision_template():
    text = """# Decision Log — Cycle 234

## Objective
- Determine the next likely failing condition inside 0x65FC before the next BIOS flash.

## Inputs
- BIOS target: 2.70
- CPU target: Athlon 3000G
- Baseline: V86/V87
- Current blocker: 0x65FC -> EFI_DEVICE_ERROR

## ChatGPT hypothesis
- [fill in]

## Claude review
- [fill in]

## Decision
- Status: ACCEPT / REJECT / RETRY / NEED MORE EVIDENCE
- Reason: [fill in]

## Next action
- [fill in]

## Risk level
- [low / medium / high]

## Flash approval
- [yes / no]
"""
    (BASE / "logs" / "decision_log_234.md").write_text(text, encoding="utf-8")

def main():
    ensure_dirs()
    cfg = load_config()
    write_dossier(cfg)
    write_chatgpt_prompt()
    write_claude_prompt()
    write_decision_template()
    print("Workflow generated for cycle 234")

if __name__ == "__main__":
    main()