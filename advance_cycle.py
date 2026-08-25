import sys
from pathlib import Path

BASE = Path(r"C:\temp\3000g")

def read_decision(cycle: int) -> str:
    path = BASE / "logs" / f"decision_cycle_{cycle}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def infer_next_prompt(decision_text: str):
    t = decision_text.lower()

    if "accept" in t:
        return {
            "goal": "Przejść do kolejnego, ściśle zdefiniowanego builda zgodnie z zaakceptowaną hipotezą. Zmienić tylko najbliższy warunek po +0x108/+0x10C lub w 0x65FC.",
            "focus": "Dodaj dokładnie jedną zmianę po zaakceptowanej hipotezie. Podaj, który fragment w 0x65FC ma zostać poprawiony i jaki wynik oczekujesz na POST.",
            "success": "Tożsamość błędu musi zostać potwierdzona przez przejście przez kolejny blok w 0x65FC, bez powrotu do EFI_DEVICE_ERROR."
        }
    if "reject" in t:
        return {
            "goal": "Zaproponować alternatywną przyczynę nie w 0x65FC, tylko w innym warunku status propagation, check condition albo innej ścieżce AHCI.",
            "focus": "Narysować alternatywną sekwencję: check -> error -> propagation -> POST07. Wskazać, dlaczego obecna hipoteza jest niepoprawna.",
            "success": "Błąd musi zostać związkowany z konkretnym warunkiem, a nie ogólną analogią."
        }
    if "need more evidence" in t:
        return {
            "goal": "Zaplanować dokładną instrumentację, która rozstrzygnie, gdzie w 0x65FC występuje pierwszy prawdziwy warunek error.",
            "focus": "Zaproponować 2-3 punkty debugowania w 0x65FC, z oczekiwanym wynikiem na każdym etapie.",
            "success": "Próba ma rozróżnić: lokalny return EFI_DEVICE_ERROR vs propagacja z niższego helpera."
        }
    return {
        "goal": "Zaproponować najbardziej prawdopodobną następną zmianę w 0x65FC i wskazać, co ją potwierdzi lub obali.",
        "focus": "Skup się na następnej gałęzi po +0x108/+0x10C i opisz mechanizm błędu.",
        "success": "Doprecyzować, który warunek w 0x65FC jest najbardziej prawdopodobny jako źródło EFI_DEVICE_ERROR."
    }

def write_dossier(next_cycle: int, goal: str, focus: str, success: str):
    dossier = f"""# BIOS Investigation Dossier — Cycle {next_cycle}

## Objective
Wykonać kolejny, ściśle zdefiniowany build w celu rozstrzygnięcia następnej hipotezy.

## Previous cycle
- Current blocker: 0x65FC -> EFI_DEVICE_ERROR
- Known fact: value from +0x108/+0x10C is non-zero

## Goal
{goal}

## Focus
{focus}

## Success criteria
{success}

## Working assumptions
- SataController is no longer the main blocker.
- AHCI dispatch is already functioning.
- Current failure is still inside the 0x65FC flow.
- Do not re-open unrelated Apriori / DEPEX unless evidence forces it.
"""
    (BASE / f"cycle_{next_cycle}" / f"dossier_cycle_{next_cycle}.md").write_text(dossier, encoding="utf-8")

def write_prompt_chatgpt(next_cycle: int, goal: str, focus: str, success: str):
    prompt = f"""You are the main BIOS patch author.

Mission:
Continue the BIOS compatibility project by proposing the next update after cycle {next_cycle - 1}.

Current state:
- SataController OK
- AHCI dispatch OK
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value from +0x108/+0x10C is non-zero
- earlier RBX == 0 theory is false

Goal:
{goal}

Focus:
{focus}

Success criteria:
{success}

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
    (BASE / "prompts" / f"chatgpt_prompt_{next_cycle}.txt").write_text(prompt, encoding="utf-8")

def write_prompt_claude(next_cycle: int, goal: str, focus: str, success: str):
    prompt = f"""You are the independent BIOS reviewer.

Review the next build proposal for cycle {next_cycle}.

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
{success}

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
    (BASE / "prompts" / f"claude_prompt_{next_cycle}.txt").write_text(prompt, encoding="utf-8")

def write_next_decision_template(next_cycle: int):
    text = f"""# Decision Log — Cycle {next_cycle}

## Objective
- Continue from the previous cycle with the next narrowed hypothesis.

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
    (BASE / "logs" / f"decision_cycle_{next_cycle}.md").write_text(text, encoding="utf-8")

def main():
    current_cycle = int(sys.argv[1]) if len(sys.argv) > 1 else 234
    next_cycle = current_cycle + 1

    decision_text = read_decision(current_cycle)
    if not decision_text:
        print(f"Brak pliku decision_cycle_{current_cycle}.md")
        raise SystemExit(1)

    data = infer_next_prompt(decision_text)
    (BASE / f"cycle_{next_cycle}").mkdir(parents=True, exist_ok=True)
    (BASE / "prompts").mkdir(parents=True, exist_ok=True)
    (BASE / "logs").mkdir(parents=True, exist_ok=True)

    write_dossier(next_cycle, data["goal"], data["focus"], data["success"])
    write_prompt_chatgpt(next_cycle, data["goal"], data["focus"], data["success"])
    write_prompt_claude(next_cycle, data["goal"], data["focus"], data["success"])
    write_next_decision_template(next_cycle)

    print(f"Utworzono nowy cykl: {next_cycle}")
    print(f"Dossier: {BASE / f'cycle_{next_cycle}' / f'dossier_cycle_{next_cycle}.md'}")
    print(f"ChatGPT: {BASE / 'prompts' / f'chatgpt_prompt_{next_cycle}.txt'}")
    print(f"Claude: {BASE / 'prompts' / f'claude_prompt_{next_cycle}.txt'}")

if __name__ == "__main__":
    main()