# Athlon 3000G on X570 Taichi — Project State

Updated: 2026-08-25

## Goal

Boot AMD Athlon 3000G Raven Ridge on ASRock X570 Taichi BIOS 2.70.

## Current baseline

Historical stable diagnostic baseline:
- V87 Apriori layout
- NvramDxe remains at index 5

Current diagnostic branch:
- V156

## Confirmed

- SataController Start() succeeds.
- AHCI dispatch succeeds.
- AHCI Start() executes.
- helper 0x2078 executes.
- helper 0x2078 calls helper 0x65FC.
- helper 0x65FC returns EFI_DEVICE_ERROR.
- V155 proved that EFI_DEVICE_ERROR originates from 0x65FC, not from status masking in 0x2078.
- value assembled from per-port fields +0x108 and +0x10C is non-zero.
- V156 therefore falsified the first local hypothesis:
  RBX == 0 -> EFI_DEVICE_ERROR.

## Current blocker

Identify the first real error condition inside helper 0x65FC after the
confirmed non-zero +0x108/+0x10C check.

Need to distinguish:

1. local generation of EFI_DEVICE_ERROR
2. propagation of EFI_DEVICE_ERROR from a lower helper

## Current expected POST

Unmodified failing path:
07

V156 diagnostic marker proving RBX != 0:
F2

## Constraints

- Do not broaden the patch beyond the unresolved AHCI branch.
- Do not revisit generic Apriori or DEPEX unless new evidence requires it.
- Do not move NvramDxe from index 5.
- Prefer instrumentation over speculative behavioural changes.
- Every proposed patch must state what hypothesis it tests.
- Every experiment must state what result would falsify the hypothesis.
- Do not modify reference ROMs.

## Binary analysis rule

For reconstruction of original control flow after RVA 0x665C,
use Ahci_body_v2.efi.

Ahci_body.efi contains V156 diagnostic instrumentation and no longer
preserves the original block beginning at RVA 0x665E.

V156 Ahci_body.efi is evidence for the observed F2 path only.