import json
import os
import sys
from pathlib import Path

from openai import OpenAI
from anthropic import Anthropic

impo

BASE = Path(r"c:\temp\3000g")
CONFIG_PATH = BASE / "bios_config.json"

def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Brak pliku konfiguracyjny: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_dirs():
    (BASE / "logs").mkdir(exist_ok=True, parents=True)
    (BASE / "prompts").mkdir(exist_ok=True, parents=True)

def build_dossier(cfg, cycle):
    return f"""# BIOS Investigation Dossier — Cycle {cycle}

## Project
- Board: {cfg['board']['manufacturer']} {cfg['board']['model']}
- BIOS target: {cfg['board']['bios_target_version']}
- CPU target: {cfg['cpu']['name']} ({cfg['cpu']['architecture']}, Family {cfg['cpu']['family']}, Model {cfg['cpu']['model']})

## Objective
{cfg['objective']}

## Current state
- Current blocker: {cfg['current_state']['current_blocker']}
- Current path: {cfg['current_state']['current_path']}

## Known facts
- SataController is no longer the primary blocker.
- AHCI dispatch is functioning.
- value from +0x108/+0x10C is non-zero.
- earlier RBX == 0 theory is false.
- error remains in helper 0x65FC.

## Working hypothesis
{cfg['working_hypothesis']}

## Next actions
- instrument next basic block after +0x108/+0x10C check
- identify the first local error condition in 0x65FC
- distinguish local EFI_DEVICE_ERROR from lower-helper propagation
"""

def build_chatgpt_prompt(dossier):
    return f"""
You are the main BIOS patch author.

Use the dossier below as source of truth.

Dossier:
{dossier}

Mission:
Propose the next BIOS modification to move the target CPU support path forward.

Constraints:
- keep the patch narrow
- focus on 0x65FC, not generic Apriori or DEPEX
- explain what call/test/compare is likely failing
- explain why this is more plausible than earlier hypotheses
- state expected POST outcome if correct
- state what would falsify the theory

Return format:
1. Hypothesis
2. Most likely BIOS area / function
3. Candidate edit or instrumentation
4. Why this is plausible
5. Expected POST behavior if correct
6. What would falsify this
7. Minimal next validation steps
"""

def build_claude_prompt(build_text):
    return f"""
You are the independent BIOS reviewer.

Review the proposal below critically.

Proposal:
{build_text}

Focus on:
- false assumptions
- branch misidentification
- hidden side effects
- alternate root causes
- missing validation
- risk of overbroad change

Return format:
1. Major concerns
2. Missing evidence
3. Alternative hypotheses
4. Safer alternative edits or instrumentation
5. Minimal validation plan
6. Final verdict: accept / reject / need more evidence
"""

def call_openai(prompt):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )
    return resp.output_text

def call_claude(prompt):
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

def summarize(build_text, review_text, cycle):
    build_l = build_text.lower()
    review_l = review_text.lower()
    text = (build_l + "\n" + review_l)

    if any(x in text for x in ["accept", "approved", "safe to flash", "clear fix"]):
        status = "ACCEPT"
        action = "Przejść do kolejnego, ściśle zdefiniowanego builda zgodnie z zaakceptowaną hipotezą."
    elif any(x in text for x in ["reject", "unsafe", "wrong assumption", "do not flash"]):
        status = "REJECT"
        action = "Odrzucić bieżącą hipotezę i zaproponować alternatywną przyczynę."
    elif any(x in text for x in ["need more evidence", "missing evidence", "not enough evidence", "more data needed"]):
        status = "NEED MORE EVIDENCE"
        action = "Dopisać brakujące dane i doprecyzować instrumentację 0x65FC."
    else:
        status = "RETRY"
        action = "Dodać nowy marker diagnostyczny w 0x65FC i sprawdzić kolejny podstawowy blok."

    decision = f"""# Decision Log — Cycle {cycle}

## ChatGPT hypothesis
{build_text}

## Claude review
{review_text}

## Status
- Status: {status}
- Reason: generated from combined build and review.

## Next action
- {action}

## Risk level
- medium

## Flash approval
- pending
"""
    return decision, status

def create_next_cycle_files(next_cycle, decision_text, cfg):
    next_dir = BASE / f"cycle_{next_cycle}"
    next_dir.mkdir(exist_ok=True, parents=True)

    # save decision
    (BASE / "logs").mkdir(exist_ok=True, parents=True)
    (BASE / "logs" / f"decision_cycle_{next_cycle}.md").write_text(decision_text, encoding="utf-8")

    # next cycle prompt generation
    dossier = build_dossier(cfg, next_cycle)
    next_prompt = f"""
You are the main BIOS patch author.

Current state:
- SataController OK
- AHCI dispatch OK
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value from +0x108/+0x10C is non-zero

Use this dossier:
{dossier}

Goal:
Continue from previous cycle with the most likely next branch in 0x65FC.

Constraints:
- narrow scope
- focus on the next failing basic block
- explain mechanism and expected POST
- if evidence is insufficient, say so explicitly

Return format:
1. Hypothesis
2. Most likely BIOS area / function
3. Exact change or instrumentation
4. Why this is plausible
5. Expected POST result
6. What would falsify this
7. Minimal validation plan
"""

    (BASE / "prompts" / f"chatgpt_prompt_{next_cycle}.txt").write_text(next_prompt, encoding="utf-8")

    review_prompt = f"""
You are the independent BIOS reviewer.

Review the next build proposal for cycle {next_cycle}.

Focus on:
- false assumptions
- hidden side effects
- missing validation
- alternate cause
- risk of overbroad patch

Return format:
1. Major concerns
2. Missing evidence
3. Alternative hypotheses
4. Safer alternative edits
5. Minimal validation plan
6. Final verdict: accept / reject / need more evidence
"""
    (BASE / "prompts" / f"claude_prompt_{next_cycle}.txt").write_text(review_prompt, encoding="utf-8")

    print(f"Przygotowano cykl {next_cycle}")

def run_cycle(cycle):
    ensure_dirs()
    cfg = load_config()
    dossier = build_dossier(cfg, cycle)
    chat_prompt = build_chatgpt_prompt(dossier)
    build_text = call_openai(chat_prompt)
    review_prompt = build_claude_prompt(build_text)
    review_text = call_claude(review_prompt)

    cycle_dir = BASE / f"cycle_{cycle}"
    cycle_dir.mkdir(exist_ok=True, parents=True)
    (cycle_dir / "build_response.txt").write_text(build_text, encoding="utf-8")
    (cycle_dir / "review_response.txt").write_text(review_text, encoding="utf-8")

    decision_text, status = summarize(build_text, review_text, cycle)
    (BASE / "logs").mkdir(exist_ok=True, parents=True)
    (BASE / "logs" / f"decision_cycle_{cycle}.md").write_text(decision_text, encoding="utf-8")

    print(f"Cykl {cycle} zakończony. Status: {status}")
    print(f"Decision log: {BASE / 'logs' / f'decision_cycle_{cycle}.md'}")

    next_cycle = cycle + 1
    create_next_cycle_files(next_cycle, decision_text, cfg)

def main():
    cycle = int(sys.argv[1]) if len(sys.argv) > 1 else 235
    run_cycle(cycle)

if __name__ == "__main__":
    main()