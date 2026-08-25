# filepath: c:\temp\3000g\run_cycle_234.ps1
$Base = "C:\temp\3000g"
$Cycle = 234
$CycleDir = Join-Path $Base "cycle_$Cycle"
$PromptsDir = Join-Path $Base "prompts"
$LogsDir = Join-Path $Base "logs"

New-Item -ItemType Directory -Force -Path $CycleDir | Out-Null
New-Item -ItemType Directory -Force -Path $PromptsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$BuildFile = Join-Path $CycleDir "build_response.txt"
$ReviewFile = Join-Path $CycleDir "review_response.txt"

$ChatPrompt = @"
You are the main BIOS patch author.

Mission:
Propose the next BIOS modification to move the target CPU support path forward.

Use the dossier below as the source of truth.

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
"@

$ClaudePrompt = @"
You are the independent BIOS reviewer.

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
"@

$PromptChat = Join-Path $PromptsDir "chatgpt_prompt_$Cycle.txt"
$PromptClaude = Join-Path $PromptsDir "claude_prompt_$Cycle.txt"

Set-Content -Path $PromptChat -Value $ChatPrompt -Encoding UTF8
Set-Content -Path $PromptClaude -Value $ClaudePrompt -Encoding UTF8

$Dossier = @"
# BIOS Investigation Dossier — Cycle $Cycle

## Objective
Uruchomić Athlona 3000G na ASRock X570 Taichi.

## Current blocker
SataController OK. AHCI Start() reaches helper 0x2078 -> 0x65FC -> EFI_DEVICE_ERROR -> POST 07.

## Known facts
- V86/V87 is active baseline.
- SataController is no longer the primary blocker.
- AHCI dispatch is enabled.
- value from +0x108/+0x10C is non-zero.
- initial RBX == 0 theory is false.
- current failure is deeper inside 0x65FC.

## Working hypothesis
Następny warunek wewnątrz helpera 0x65FC, po sprawdzeniu +0x108/+0x10C, prowadzi do EFI_DEVICE_ERROR.

## Next actions
- dodać marker po pierwszym checku w 0x65FC
- rozbić 0x65FC na podstawowe bloki
- zidentyfikować pierwszy warunek prowadzący do EFI_DEVICE_ERROR
- rozróżnić lokalny return od propagacji statusu z niższego helpera
"@

$DossierPath = Join-Path $CycleDir "dossier_cycle_$Cycle.md"
Set-Content -Path $DossierPath -Value $Dossier -Encoding UTF8

Write-Host ""
Write-Host "Live loop for cycle $Cycle initialized."
Write-Host "Prompt for ChatGPT: $PromptChat"
Write-Host "Prompt for Claude: $PromptClaude"
Write-Host ""
Write-Host "Po dodaniu odpowiedzi z ChatGPT i Claude zapisz je do:"
Write-Host "  ChatGPT: $BuildFile"
Write-Host "  Claude:  $ReviewFile"
Write-Host ""
Write-Host "Uruchom:"
Write-Host "  python C:\temp\3000g\summarize_cycle_234.py"