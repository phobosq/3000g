# Decision Log — Cycle 234

## ChatGPT hypothesis
1. **Hypothesis**

Najbardziej prawdopodobny następny punkt awarii w `0x65FC` to **pierwszy status-returning `call` wykonywany po potwierdzonym checku `RBX != 0`, wraz z bezpośrednim `EFI_ERROR(Status)` / `test rax,rax ; js ...` prowadzącym do wspólnego bloku `EFI_DEVICE_ERROR`**.

Robocza hipoteza dla Cycle 234:

> `0x65FC` poprawnie uzyskuje 64-bitową wartość z `+0x108/+0x10C`, ale następna operacja wykonywana z użyciem tej wartości — najpewniej programowanie/walidacja zasobu portu lub operacja DMA/MMIO — zwraca status błędny albo nie spełnia kolejnego warunku. `0x65FC` następnie lokalnie konwertuje ten przypadek na `EFI_DEVICE_ERROR`.

Nie proponowałbym jeszcze bypassu samego `EFI_DEVICE_ERROR`. Najpierw trzeba rozstrzygnąć **czy źródłem jest następny `call`, czy lokalny `cmp/test` po nim**.

---

2. **Most likely BIOS area / function**

Obszar pozostaje bardzo wąski:

```text
AHCI.Start()
  └─ 0x2078
       └─ 0x65FC
            ├─ load +0x108/+0x10C
            ├─ compose 64-bit value → RBX
            ├─ RBX == 0 ? EFI_DEVICE_ERROR   ← V156: NIE
            │
            └─ NEXT BASIC BLOCK             ← cel Cycle 234
                 ├─ call X
                 ├─ test/cmp result
                 └─ branch → error
```

Szczególnie interesujący jest **pierwszy `call` dominowany przez blok `RBX != 0`**, jeżeli po nim występuje jeden z typowych wzorców:

```asm
call    sub_xxxx
test    rax, rax
js      error
```

lub:

```asm
call    sub_xxxx
cmp     eax, 0
jne     error
```

albo lokalna walidacja wartości/adresu:

```asm
test/cmp rbx, ...
jcc      device_error
```

Nie wracałbym na tym etapie ani do Apriori, ani do DEPEX, ani do `0x2078`.

---

3. **Candidate edit or instrumentation**

### Proponowany V157 / Cycle 234 patch

Zamiast instrumentować dopiero exit `0x65FC`, wstawić **dwa rozróżnialne markery wokół pierwszego istotnego `call` po checku RBX**:

```text
marker A → bezpośrednio przed CALL
CALL
marker/status probe B → bezpośrednio po CALL, przed EFI_ERROR/test/cmp
```

Najlepszy wariant diagnostyczny to nie tylko marker obecności, lecz sklasyfikowanie `RAX`:

```text
RAX == EFI_SUCCESS       → marker B0
RAX has EFI_ERROR bit    → marker B1
```

Jeżeli bezpiecznie mieści się patch, dodatkowo trzeci marker:

```text
marker C → taken error branch po test/cmp
```

Czyli logicznie:

```asm
; RBX != 0 confirmed

POST A
call    next_helper

; preserve RAX
test    rax, rax
js      status_error_marker

POST B
; original flow
...
```

**Nie zmieniałbym jeszcze wyniku `call` na `EFI_SUCCESS`.**

Jeżeli okaże się, że między `RBX` checkiem a error blockiem **nie ma żadnego calla**, analogicznie instrumentować pierwszy następny `cmp/test` oraz obie strony jego conditional branch.

---

4. **Why this is plausible**

V155 i V156 mocno zmieniły priorytety hipotez:

```text
V155:
0x65FC → EFI_DEVICE_ERROR

V156:
(+0x10C << 32) | +0x108 != 0
```

Zatem wcześniejszy model:

```text
missing/null resource
→ RBX == 0
→ local EFI_DEVICE_ERROR
```

jest już empirycznie odrzucony.

Najbardziej prawdopodobna klasa błędu przesuwa się więc o jeden basic block dalej:

```text
resource exists
        ↓
resource is consumed / programmed / validated
        ↓
operation fails
        ↓
EFI_DEVICE_ERROR
```

To jest znacznie bardziej prawdopodobne niż powrót do dispatchu AHCI, ponieważ mamy już jednoznaczny ciąg wykonania:

```text
SataController OK
AHCI dispatched
AHCI.Start entered
0x2078 entered
0x65FC entered
RBX resource exists
0x65FC returns error
```

Innymi słowy: teraz szukamy **semantycznej niezgodności zasobu Raven Ridge**, a nie braku wykonania modułu.

---

5. **Expected POST behavior if correct**

Przy samej instrumentacji oczekuję jednego z dwóch rozstrzygających wyników.

### Wariant A — podrzędny `call` jest źródłem

```text
marker-before-call
→ marker indicating EFI_ERROR
→ 07
```

To oznacza:

> `0x65FC` nie tworzy błędu samodzielnie w następnym warunku; propaguje lub mapuje failure zwrócony przez niższą funkcję.

Następny cykl schodzi wtedy **do tego konkretnego helpera**.

### Wariant B — `call` wraca sukcesem

```text
marker-before-call
→ SUCCESS marker
→ 07
```

Wtedy blockerem jest kolejny lokalny:

```asm
cmp/test
jcc error
```

i następny build powinien instrumentować **wartości operandów tego właśnie compare**.

Jeśli późniejszy eksperymentalny bypass właściwego warunku okaże się poprawny, oczekujemy odejścia od:

```text
07
```

i pojawienia się **nowego, późniejszego POST code / następnego markera AHCI**, niekoniecznie od razu pełnego POST.

---

6. **What would falsify this**

Hipoteza o „następnym status-returning callu” zostaje obalona, jeśli:

* pierwszy `call` po `RBX != 0` zwróci jednoznacznie `EFI_SUCCESS`,
* wszystkie kolejne status-returning calle do momentu error exit również zwrócą sukces,
* albo control flow ominie przewidywany `EFI_ERROR` branch, a mimo tego `0x65FC` zakończy się `EFI_DEVICE_ERROR`.

Wtedy należy szukać **lokalnego compare**, np.:

```text
alignment
range
capability bit
port state
register readback
mask != expected
```

Jeżeli natomiast marker przed następnym blokiem w ogóle się nie pojawi, falsyfikuje to nasze obecne rozumienie CFG — istnieje wcześniejsza ścieżka z `RBX != 0` bezpośrednio do error exit.

---

7. **Minimal next validation steps**

8. W `0x65FC` znaleźć **pierwszy conditional branch po potwierdzonym `RBX != 0`**, ze szczególnym uwzględnieniem pierwszego `call`.

9. Zbudować Cycle 234 tak, aby rozróżniał tylko trzy stany:

```text
A = osiągnięto następny basic block
B = następny CALL zwrócił EFI_SUCCESS
C = następny CALL zwrócił EFI_ERROR
```

3. Nie bypassować jeszcze błędu.
4. Jeżeli wynik to `C → 07`, następny cel to **callee tego jednego calla**.
5. Jeżeli wynik to `B → 07`, instrumentować **pierwszy `cmp/test + jcc` za nim**, zapisując/oznaczając obie gałęzie.

### Rekomendacja do następnego BIOS-u

**Cycle 234 powinien być czystym discriminator buildem dla pierwszego basic blocku po `RBX != 0`, a nie kolejnym funkcjonalnym patchem.**

Mamy już na tyle wąski failure cone, że jeden dobrze umieszczony probe powinien rozstrzygnąć, czy schodzimy **do następnego helpera**, czy zostajemy **w lokalnej logice `0x65FC`**.

## Claude review
## Recenzja niezależnego reviewera BIOS — Cycle 234 (dyskryminator basic-block w 0x65FC)

### 1. Major concerns

- **Cała hipoteza zakłada konkretny kształt CFG (call → test rax,rax/js → error), którego nikt jeszcze nie potwierdził dekompilacją.** Dokument sam przyznaje "nie wiemy, czy jest call, czy cmp/test" — a mimo to proponowany patch (marker A/B/C wokół "pierwszego calla") zakłada z góry, że call istnieje i że jest pierwszym elementem w kolejnym basic blocku. Jeśli następny blok zaczyna się od `cmp`/`test`/`lea`/dostępu do pamięci bez wywołania funkcji, marker A trafi w złe miejsce lub w ogóle się nie skompiluje sensownie względem rzeczywistego kodu.
- **Założenie konwencji wywołania x64 (RAX = status) nie zostało zweryfikowane dla tego konkretnego calla.** To może być helper zwracający BOOLEAN, wskaźnik, czy coś, co tylko przypadkiem mieści się w EAX/RAX z ustawionym bitem znaku — patch "test rax,rax; js error" jako założenie interpretacyjne jest ryzykowny, bo `js` (sign flag) niekoniecznie odpowiada konwencji `EFI_ERROR()` (najwyższy bit 64-bit), a instrumentacja może błędnie klasyfikować B/C.
- **"Preserve RAX" w kodzie patcha jest niebezpieczne bez znajomości pełnego ABI tej funkcji.** Jeśli oryginalny kod używa RAX/RCX/RDX/R8-R11 jako scratch zaraz po callu (typowe dla MSVC-skompilowanego AMI/EDK2 binarnego kodu), wstrzyknięcie dodatkowych instrukcji (POST out + test + conditional jump) między `call` a właściwym użyciem wyniku może nadpisać flagi (RFLAGS) lub rejestry, których dalszy kod się spodziewa nietkniętych. To nie jest tylko ryzyko teoretyczne — to dokładnie ten typ overbroad/side-effect change, przed którym trzeba ostrzec.
- **Brak dowodu, że "pierwszy call po RBX != 0" jest w ogóle na ścieżce prowadzącej do EFI_DEVICE_ERROR.** Mogą istnieć dwa lub więcej rozłącznych bloków między potwierdzonym warunkiem `RBX != 0` a punktem zwrotu błędu (np. dodatkowe early-exit na innych warunkach, pętla retry, kilka niezależnych walidacji). Zakładanie liniowej sekwencji "RBX!=0 → call → test → error" jest uproszczeniem, które może pominąć rozgałęzienia.

### 2. Missing evidence

- Brak jakiejkolwiek dekompilacji/disasemblacji 0x65FC pokazującej rzeczywisty basic block bezpośrednio po skoku warunkowym `RBX == 0`. Cały plan Cycle 234 jest budowany na spekulacji o kształcie kodu, nie na jego treści.
- Brak potwierdzenia liczby instrukcji/bloków między `RBX != 0` a `ret EFI_DEVICE_ERROR` — czy to jeden blok, czy pięć.
- Brak informacji, czy funkcja w ogóle zawiera jakikolwiek `call` przed error exitem, czy błąd powstaje wyłącznie z lokalnych porównań (co dokument sam dopuszcza jako "Wariant B", ale i tak proponuje zacząć od instrumentacji calla).
- Brak analizy, czy 0x65FC ma więcej niż jedną ścieżkę zwrotu `EFI_DEVICE_ERROR` (możliwość, którą podniosłem w poprzedniej recenzji, wciąż nieadresowana).
- Brak weryfikacji stanu rejestrów HBA (GHC/CAP/PI/BOH) w tym punkcie — nadal nieobecna z poprzedniej rundy, a to wciąż jedna z najbardziej prawdopodobnych przyczyn niepowodzenia "resource consumed/programmed" na etapie post-RBX.
- Brak potwierdzenia, że +0x108/+0x10C w ogóle reprezentuje "zasób" (np. adres BAR/MMIO), a nie coś, co tylko przypadkowo jest niezerowe (poison/heap garbage — ryzyko podniesione poprzednio i wciąż nierozstrzygnięte).

### 3. Alternative hypotheses

- **Błąd może w ogóle nie być w następnym basic blocku po RBX-check, lecz w oddzielnej wcześniejszej gałęzi, która scala się (merge point) z tą, którą testujemy** — tj. `RBX != 0` mogło nie być jedynym warunkiem prowadzącym do tego samego error exitu; instrumentacja jednej gałęzi nie wyklucza równoległej.
- **Możliwe, że kolejny "call" to nie funkcja walidująca zasób, lecz coś w rodzaju `gBS->WaitForEvent`/`Stall`/pollowanie timera**, którego niepowodzenie wynika z wcześniej zdiagnozowanych problemów projektu z Timer Arch Protocol / niekompletnym CPU_ARCH chain — czyli powrót do już znanego ryzyka projektu, a nie nowa "semantyczna niezgodność zasobu Raven Ridge".
- **+0x108/+0x10C mogą być niepowiązane z faktycznym parametrem calla** — dokument zakłada, że "RBX skomponowane z tych pól" jest przekazywane do następnej funkcji, ale nie ma dowodu, że RBX w ogóle jest argumentem calla (może być użyte tylko do lokalnego warunku, a call operuje na zupełnie innych rejestrach/strukturze).
- **Alternatywnie, błąd może wynikać z nieprawidłowego mapowania MMIO/BAR wcześniej w łańcuchu PciRootBridge/PciBus (F10 donor)** — spójne z udokumentowaną w projekcie historią problemów z RootBridgeIO/PCI_IO. To nadal nie zostało wykluczone i jest tańsze do zweryfikowania niż drążenie kolejnych basic bloków 0x65FC.

### 4. Safer alternative edits or instrumentation

- Zanim wstawi się jakikolwiek patch oparty na założeniu "call → test rax,rax → js", **wykonać czystą dekompilację/dysasemblację bloku bezpośrednio po `RBX != 0`** (nawet ręczną, offline) i dopiero na tej podstawie projektować markery — nie zgadywać kształtu kodu.
- Jeśli dekompilacja nie jest możliwa w tym cyklu, **ograniczyć patch do jednego markera "reached next block" bez żadnej próby klasyfikacji RAX/branch**, żeby zweryfikować samo dotarcie do tego miejsca bez ryzyka zaburzenia rejestrów/flag przed nieznaną instrukcją.
- Unikać wstawiania `test rax, rax` / warunkowego skoku w kodzie instrumentacyjnym, dopóki nie wiadomo, że RAX rzeczywiście niesie status — zamiast tego zrzucić surową wartość RAX (lub kilku rejestrów) do POST port w formie rozbitej na bajty, bez interpretacji.
- Zachować oryginalne flagi/rejestry nietknięte tak długo, jak to możliwe — jeśli trzeba użyć POST out (zwykle przez port I/O, co nadpisuje AL i potencjalnie flagi), zapisać i odtworzyć pełny kontekst (`pushfq`/`push rax` itd.) wokół instrumentacji, nie tylko RAX.
- Równolegle (tańszy, niezależny eksperyment) zweryfikować stan rejestrów HBA i mapowania BAR w tym punkcie — to może rozstrzygnąć hipotezę alternatywną bez dalszego drążenia w głąb 0x65FC.

### 5. Minimal validation plan before next flash

1. Uzyskać realną dekompilację bloku po `RBX != 0` (choćby częściową) — warunek konieczny przed zaprojektowaniem precyzyjnego patcha.
2. Jeśli niedostępna: build z **jednym** markerem "reached-next-block", zero interpretacji RAX, zero conditional logic w patchu.
3. Dopiero po potwierdzeniu, że blok jest osiągany i że jest tam faktycznie `call`, zaprojektować wariant z klasyfikacją sukces/błąd — i to z zachowaniem pełnego kontekstu rejestrów/flag.
4. Równolegle zebrać zrzut rejestrów HBA (GHC/CAP/PI) w tym punkcie jako niezależną ścieżkę weryfikacji.
5. Nie łączyć instrumentacji z żadnym bypassem błędu w tym samym buildzie — Cycle 234 ma pozostać czysto diagnostyczny, zgodnie z własną deklaracją dokumentu.

### 6. Final verdict

**Need more evidence — odrzucam projekt patcha w obecnej formie.** Plan zakłada nieznany kształt kodu (call + test rax,rax + js) bez dekompilacji, ryzykuje naruszenie rejestrów/flag nieznaną instrumentacją, i nie wyklucza alternatywnych hipotez (wielościeżkowy error exit, problem z BAR/MMIO wcześniej w łańcuchu). Rekomenduję najpierw dekompilację lub minimalny, bezinterpretacyjny marker "reached next block", zanim powstanie jakikolwiek patch klasyfikujący RAX.

## Status
- Status: NEED MORE EVIDENCE
- Reason: generated from the combined build and review analysis.

## Next action
- Dopisać brakujące dane i zidentyfikować dokładnie kolejny punkt instrumentacji w 0x65FC. Nie robić kolejnego flashu bez tego.

## Risk level
- medium

## Flash approval
- pending
