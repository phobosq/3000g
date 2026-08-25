param(
    [int]$Cycle = 234
)

$Base = "C:\temp\3000g"
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

Current state:
- SataController OK
- AHCI dispatch OK
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value from +0x108/+0x10C is non-zero
- earlier RBX == 0 theory is false

Cycle: $Cycle

Constraints:
- keep scope narrow
- focus on the next likely branch inside 0x65FC
- explain the likely cause in terms of a call / compare / test / error edge
- explain why this is more plausible than previous hypotheses
- state what would invalidate the theory
- keep output technical and evidence-based

Return format:
1. Hypothesis
2. Most likely BIOS area / function
3. Candidate edit or instrumentation
4. Why this is plausible
5. Expected POST behavior
6. What would falsify this
7. Minimal validation plan
"@

$ClaudePrompt = @"
You are the independent BIOS reviewer.

Review the next build proposal for cycle $Cycle.

Current state:
- SataController OK
- AHCI dispatch OK
- helper 0x2078 reaches helper 0x65FC
- helper 0x65FC returns EFI_DEVICE_ERROR
- POST 07
- value at +0x108/+0x10C is non-zero

Return format:
1. Major concerns
2. Missing evidence
3. Alternative hypotheses
4. Safer alternative edits or instrumentation
5. Minimal validation plan
6. Final verdict: accept / reject / need more evidence
"@

$PromptChat = Join-Path $PromptsDir "chatgpt_prompt_$Cycle.txt"
$PromptClaude = Join-Path $PromptsDir "claude_prompt_$Cycle.txt"

Set-Content -Path $PromptChat -Value $ChatPrompt -Encoding UTF8
Set-Content -Path $PromptClaude -Value $ClaudePrompt -Encoding UTF8

Write-Host "Cycle $Cycle initialized."
Write-Host "ChatGPT prompt: $PromptChat"
Write-Host "Claude prompt:  $PromptClaude"
Write-Host ""
Write-Host "Po dodaniu odpowiedzi wpisz:"
Write-Host "  ChatGPT -> $BuildFile"
Write-Host "  Claude  -> $ReviewFile"
Write-Host ""
Write-Host "A potem uruchom:"
Write-Host "  python $Base\summarize_cycle.py $Cycle"