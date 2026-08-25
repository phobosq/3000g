# BIOS Investigation Dossier — Cycle 234

## Project
- Board: ASRock X570 Taichi
- BIOS target: 2.70
- CPU target: Athlon 3000G (Raven Ridge, Family 17h, Model 11h)
- Status date: 2026-08-24

## Objective
Doprowadzić do poprawnej inicjalizacji CPU na X570 Taichi z BIOS 2.70 poprzez mapowanie brakującego wsparcia Raven Ridge.

## Current blocker
Blokada znajduje się wewnątrz helpera 0x65FC po przejściu pierwszego warunku z wartości z +0x108/+0x10C.

## Current path
DXE Dispatcher -> SataController -> AHCI Start() -> helper 0x2078 -> helper 0x65FC -> EFI_DEVICE_ERROR -> POST 07

## Known facts
- V86/V87 is the active baseline.
- SataController is no longer the primary blocker.
- AHCI dispatch is functional after forced DXE ordering.
- The value assembled from +0x108/+0x10C is non-zero.
- The initial RBX == 0 theory is invalid.
- The error is deeper inside 0x65FC.

## Working hypothesis
Po potwierdzeniu, że złożona wartość z +0x108/+0x10C jest niezerowa, wewnętrzny kolejny warunek / call w helperze 0x65FC generuje EFI_DEVICE_ERROR i powoduje POST 07.

## Next actions
- Dodać kolejny marker diagnostyczny poza pierwszym checkiem w 0x65FC.
- Rozbić cały CFG 0x65FC na kolejne basic blocks.
- Zidentyfikować pierwszy warunek po checku +0x108/+0x10C, który prowadzi do EFI_DEVICE_ERROR.
- Instrumentować status zaraz po każdym następnym callu, a nie wyłącznie po return.
- Rozróżniać: lokalny return EFI_DEVICE_ERROR vs propagację EFI_ERROR(Status) z niższego helpera.
- Unikać powrotu do SataController / Apriori / DEPEX, dopóki nie znajdzie się konkretny warunek wewnątrz 0x65FC.

## Validated progress
- v138: SataController Start() kończy się poprawnie => SataController przestał być głównym blockerem.
- v140: E1, AHCI zaczyna być wykonywany => Wymuszony DXE Apriori i dispatch AHCI są poprawnie aktywne.
- v145: E7, LocateHandleBuffer(ByProtocol, AHCI_BUS_INIT_PROTOCOL) => Problem nie jest tylko w dispatchu; potrzebne jest wejście w AHCI Start().
- v150: POST 07 => Występuje już realny błąd, nie tylko marker diagnostyczny.
- v155: 0x65FC -> EFI_DEVICE_ERROR => Helper 0x65FC jest bezpośrednim źródłem błędu.
- v156: RBX != 0, wartość z +0x108/+0x10C != 0 => Pierwszy lokalny warunek RBX == 0 nie jest przyczyną. Problem jest głębiej w 0x65FC.

## Candidate next build
- Next version hint: V157
- Expected behavior: Dodatkowy marker na kolejnym bloku wewnątrz 0x65FC; nie ma sensu wracać do wcześniejszych warstw dopóki nie wyjdzie dokładny source of error.
