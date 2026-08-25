from pathlib import Path
import json

BASE = Path(r"C:\temp\3000g")
CYCLE = 234
NEXT_CYCLE = CYCLE + 1
NEXT_DIR = BASE / f"cycle_{NEXT_CYCLE}"
PROMPTS_DIR = BASE / "prompts"
LOGS_DIR = BASE / "logs"
DECISION_PATH = LOGS_DIR / f"decision_cycle_{CYCLE}.md"

def read_decision():
    if not DECISION_PATH.exists():
        return None
    text = DECISION_PATH.read_text(encoding="utf-8")
    return text

def infer_next_prompt(decision_text: str):
    text = decision_text.lower()

    if "accept" in text:
        return {
            "goal": "Przejść do kolejnego, ściśle zdefiniowanego builda zgodnie z zaakceptowaną hipotezą. Uwaga: nie rozciągać zakresu. Zmienić tylko najbliższy warunek po +0x108/+0x10C lub w 0x65FC.",
            "focus": "Dodaj dokładnie jedną zmianę po zaakceptowanej hipotezie. Podaj, który fragment w 0x65FC ma zostać poprawiony i jaki wynik oczekujesz na POST.",
            "status_prompt": "Aby ten build był uznany za poprawny, musi pokazać przejście przez kolejny blok w 0x65FC i nie może wrócić do EFI_DEVICE_ERROR."
        }
    if "reject" in text:
        return {
            "goal": "Zaproponować alternatywną przyczynę nie w 0x65FC, tylko w innym warunku status propagation, check condition albo innej ścieżce AHCI.",
            "focus": "Narysować alternatywną sekwencję: check -> error -> propagation -> POST07. Wskazać, dlaczego obecna hipoteza jest niepoprawna.",
            "status_prompt": "Tożsamość błędu musi być uzasadniona przez kolejny warunek, a nie przez ogólną analogię."
        }
    if "need more evidence" in text:
        return {
            "goal": "Zaplanować dokładną instrumentację, która rozstrzygnie, gdzie w 0x65FC występuje pierwszy prawdziwy warunek error.",
            "focus": "Zaproponować 2-3 punkty debugowania w 0x65FC, z oczekiwanym wynikiem na każdym etapie.",
            "status_prompt": "Próba ma rozróżnić: lokalny return EFI_DEVICE_ERROR vs propagacja z niższego helpera."
        }
    return {
        "goal": "Zaproponować najbardziej prawdopodobną następną zmianę w 0x65FC i wskazać, co ją potwierdzi lub obali.",
        "focus": "Skup się na następnej gałęzi po +0x108/+0x10C i opisz mechanizm błędu.",
        "status_prompt": "Doprecyzować, który warunek w 0x65FC jest najbardziej prawdopodobny jako źródło EFI_DEVICE_ERROR."
    }

def write_dossier(goal, focus, status_prompt):
    text = f"""# BIOS Investigation Dossier — Cycle {NEXT_CYCLE}

## Objective
Wykonać kolejny, ściśle zdefiniowany build w celu rozstrzygnięcia następnej hipotezy.

## Previous cycle
- Cycle 234
- Current blocker: 0x65FC -> EFI_DEVICE_ERROR
- Main assumption: the error is deeper in helper flow, after initial +0x108/+0x10C check

## Goal
{goal}

## Focus
{focus}

## Success criteria
{status_prompt}

## Working assumptions
- SataController is no longer the main blocker.
- AHCI dispatch is already functioning.
- Current failure is still inside the 0x65FC flow.
- Do not re-open unrelated Apriori / DEPEX unless absolutely required.

## Next build hint
Generate the narrowest possible diagnostic or patch change to answer the current unresolved question.
"""
    (NEXT_DIR / f"dossier_cycle_{NEXT_CYCLE}.md").write_text(text, encoding="utf-8")

def write_prompt_chatgpt(goal, focus, status_prompt):
    prompt = f"""You are the main BIOS patch author.

Mission:
Continue the BIOS compatibility project by proposing the next update after cycle 234.

Current state:
- SataController OK
- AHCI dispatch OK
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value from +0x108/+0x10C is non-zero
- earlier RBX == 0 hypothesis is false

Goal:
{goal}

Focus:
{focus}

Success criteria:
{status_prompt}

Constraints:
- do not broaden the patch beyond the current unresolved branch
- do not revisit generic Apriori / DEPEX unless evidence forces it
- explain what change is being made and why
- explain what would falsify this theory
- state the expected POST behavior
- keep the output technical and minimal

Return format:
1. Hypothesis
2. Most likely BIOS area / function
3. Exact change or instrumentation
4. Why this is plausible
5. Expected POST result
6. What would falsify this
7. Minimal validation plan
"""
    (PROMPTS_DIR / f"chatgpt_prompt_{NEXT_CYCLE}.txt").write_text(prompt, encoding="utf-8")

def write_prompt_claude(goal, focus, status_prompt):
    prompt = f"""You are the independent BIOS reviewer.

Review the next build proposal for cycle {NEXT_CYCLE}.

Current state:
- SataController OK
- AHCI dispatch OK
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value from +0x108/+0x10C is non-zero

Goal:
{goal}

Focus:
{focus}

Success criteria:
{status_prompt}

Review checklist:
- false assumptions
- hidden side effects
- invalid branch mapping
- missing validation
- alternate cause
- risk of overbroad patch

Return format:
1. Major concerns
2. Missing evidence
3. Alternative hypotheses
4. Safer alternative edits or instrumentation
5. Minimal validation plan
6. Final verdict: accept / reject / need more evidence
"""
    (PROMPTS_DIR / f"claude_prompt_{NEXT_CYCLE}.txt").write_text(prompt, encoding="utf-8")

def write_next_decision_template():
    text = f"""# Decision Log — Cycle {NEXT_CYCLE}

## Objective
- Continue from cycle 234 with the next narrowed hypothesis.

## Inputs
- Current blocker: 0x65FC -> EFI_DEVICE_ERROR
- Current known fact: +0x108/+0x10C non-zero

## ChatGPT hypothesis
- [fill in]

## Claude review
- [fill in]

## Decision
- Status: ACCEPT / REJECT / NEED MORE EVIDENCE / RETRY
- Reason: [fill in]

## Next action
- [fill in]

## Flash approval
- [yes / no]
"""
    (LOGS_DIR / f"decision_cycle_{NEXT_CYCLE}.md").write_text(text, encoding="utf-8")

def main():
    decision_text = read_decision()
    if decision_text is None:
        print(f"Brak decyzji z cyklu {CYCLE}: {DECISION_PATH}")
        raise SystemExit(1)

    data = infer_next_prompt(decision_text)
    NEXT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    write_dossier(data["goal"], data["focus"], data["status_prompt"])
    write_prompt_chatgpt(data["goal"], data["focus"], data["status_prompt"])
    write_prompt_claude(data["goal"], data["focus"], data["status_prompt"])
    write_next_decision_template()

    print(f"Utworzono cykl {NEXT_CYCLE}")
    print(f"Dossier: {NEXT_DIR / f'dossier_cycle_{NEXT_CYCLE}.md'}")
    print(f"ChatGPT prompt: {PROMPTS_DIR / f'chatgpt_prompt_{NEXT_CYCLE}.txt'}")
    print(f"Claude prompt: {PROMPTS_DIR / f'claude_prompt_{NEXT_CYCLE}.txt'}")

if __name__ == "__main__":
    main()