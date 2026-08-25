import sys
from pathlib import Path

BASE = Path(r"C:\temp\3000g")

def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def detect_status(build: str, review: str) -> str:
    text = (build + "\n" + review).lower()

    if any(k in text for k in ["accept", "approved", "safe to flash", "clear fix", "good next step"]):
        return "ACCEPT"
    if any(k in text for k in ["reject", "not safe", "unsafe", "do not flash", "wrong assumption"]):
        return "REJECT"
    if any(k in text for k in ["need more evidence", "missing evidence", "more data needed", "not enough evidence"]):
        return "NEED MORE EVIDENCE"
    return "RETRY"

def decide_next_action(build: str, review: str) -> str:
    text = (build + "\n" + review).lower()

    if any(k in text for k in ["need more evidence", "missing evidence", "more data needed", "not enough evidence"]):
        return "Dopisać brakujące dane i zidentyfikować dokładnie kolejny punkt instrumentacji w 0x65FC. Nie robić kolejnego flashu bez tego."
    if any(k in text for k in ["reject", "unsafe", "wrong assumption", "do not flash"]):
        return "Odrzucić bieżącą hipotezę i zaproponować alternatywną przyczynę: inny warunek po +0x108/+0x10C, inna propagacja EFI_DEVICE_ERROR albo inna ścieżka status propagation."
    if any(k in text for k in ["accept", "approved", "safe to flash"]):
        return "Przejść do kolejnego, ściśle zdefiniowanego builda zgodnie z zaakceptowaną hipotezą."
    return "Dodać nowy marker diagnostyczny w 0x65FC i sprawdzić kolejny podstawowy blok po pierwszym warunku."

def build_decision(cycle: int, build: str, review: str) -> str:
    status = detect_status(build, review)
    next_action = decide_next_action(build, review)

    return f"""# Decision Log — Cycle {cycle}

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

def main():
    cycle = int(sys.argv[1]) if len(sys.argv) > 1 else 234
    cycle_dir = BASE / f"cycle_{cycle}"
    build_path = cycle_dir / "build_response.txt"
    review_path = cycle_dir / "review_response.txt"
    log_path = BASE / "logs" / f"decision_cycle_{cycle}.md"

    if not build_path.exists() or not review_path.exists():
        print("Brakuje odpowiedzi.")
        print(f"ChatGPT: {build_path}")
        print(f"Claude: {review_path}")
        print("Wypełnij oba pliki, a potem uruchom ponownie.")
        raise SystemExit(1)

    build_text = read_text(build_path)
    review_text = read_text(review_path)
    decision = build_decision(cycle, build_text, review_text)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(decision, encoding="utf-8")

    print(f"Zapisano decyzję: {log_path}")

    # opcjonalnie uruchom automatyczne przejście do następnego cyklu
    import subprocess, sys as s
    subprocess.run([s.executable, str(BASE / "advance_cycle.py"), str(cycle)], check=False)

if __name__ == "__main__":
    main()