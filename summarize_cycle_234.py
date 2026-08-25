from pathlib import Path
import re

BASE = Path(r"C:\temp\3000g")
CYCLE = 234
CYCLE_DIR = BASE / f"cycle_{CYCLE}"
BUILD_PATH = CYCLE_DIR / "build_response.txt"
REVIEW_PATH = CYCLE_DIR / "review_response.txt"
LOG_PATH = BASE / "logs" / f"decision_cycle_{CYCLE}.md"

def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def detect_status(build: str, review: str) -> str:
    text = (build + "\n" + review).lower()
    if any(x in text for x in ["accept", "approved", "safe to flash", "clear fix"]):
        return "ACCEPT"
    if any(x in text for x in ["reject", "not safe", "unsafe", "do not flash"]):
        return "REJECT"
    if any(x in text for x in ["need more evidence", "missing evidence", "not enough evidence", "more data needed"]):
        return "NEED MORE EVIDENCE"
    return "RETRY"

def decide_next_action(build: str, review: str) -> str:
    text = (build + "\n" + review).lower()

    if "missing evidence" in text or "need more evidence" in text or "more data needed" in text:
        return "Dopisać brakujące dane i zidentyfikować dokładnie kolejny punkt instrumentacji w 0x65FC. Nie robić kolejnego flashu bez tego."

    if "reject" in text or "unsafe" in text or "do not flash" in text:
        return "Odrzucić bieżącą hipotezę i zaproponować alternatywną przyczynę: inny warunek po +0x108/+0x10C, inna propagacja EFI_DEVICE_ERROR, albo inna ścieżka Status propagation."

    if "accept" in text or "approved" in text:
        return "Przejść do kolejnego, ściśle zdefiniowanego builda: najwęższa modyfikacja w 0x65FC zgodna z zaakceptowaną hipotezą."

    return "Dodać nowy marker diagnostyczny w 0x65FC i sprawdzić kolejny podstawowy blok po pierwszym warunku."

def build_decision(build: str, review: str) -> str:
    status = detect_status(build, review)
    next_action = decide_next_action(build, review)

    decision = f"""# Decision Log — Cycle {CYCLE}

## ChatGPT hypothesis
{build.strip()}

## Claude review
{review.strip()}

## Status
- Status: {status}
- Reason: generated from the combined build and review analysis.

## Next action
- {next_action}

## Risk level
- medium

## Flash approval
- pending
"""

    return decision

def main():
    if not BUILD_PATH.exists() or not REVIEW_PATH.exists():
        print("Brakuje jednej z odpowiedzi.")
        print(f"ChatGPT: {BUILD_PATH}")
        print(f"Claude: {REVIEW_PATH}")
        print("Wypełnij oba pliki, a potem uruchom ponownie.")
        raise SystemExit(1)

    build_text = read_text(BUILD_PATH)
    review_text = read_text(REVIEW_PATH)

    decision = build_decision(build_text, review_text)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(decision, encoding="utf-8")

    print(f"Zapisano decyzję: {LOG_PATH}")

    # Automatyczne przejście do kolejnego cyklu
    import subprocess, sys
    py = sys.executable
    subprocess.run([py, str(BASE / "advance_cycle_234.py")], check=False)

if __name__ == "__main__":
    main()