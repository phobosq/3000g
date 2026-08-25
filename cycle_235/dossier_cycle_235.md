# BIOS Investigation Dossier — Cycle 235

## Objective
Wykonać kolejny, ściśle zdefiniowany build w celu rozstrzygnięcia następnej hipotezy.

## Previous cycle
- Cycle 234
- Current blocker: 0x65FC -> EFI_DEVICE_ERROR
- Main assumption: the error is deeper in helper flow, after initial +0x108/+0x10C check

## Goal
Zaplanować dokładną instrumentację, która rozstrzygnie, gdzie w 0x65FC występuje pierwszy prawdziwy warunek error.

## Focus
Zaproponować 2-3 punkty debugowania w 0x65FC, z oczekiwanym wynikiem na każdym etapie.

## Success criteria
Próba ma rozróżnić: lokalny return EFI_DEVICE_ERROR vs propagacja z niższego helpera.

## Working assumptions
- SataController is no longer the main blocker.
- AHCI dispatch is already functioning.
- Current failure is still inside the 0x65FC flow.
- Do not re-open unrelated Apriori / DEPEX unless absolutely required.

## Next build hint
Generate the narrowest possible diagnostic or patch change to answer the current unresolved question.
