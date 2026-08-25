# Athlon 3000G na ASRock X570 Taichi
## Stan projektu — 2026-08-24

### Cel

Uruchomić **Athlona 3000G (Raven Ridge / Family 17h Model 11h)** na **ASRock X570 Taichi**, bazując na BIOS-ie **2.70** i transplantując / adaptując brakujące elementy wsparcia Raven Ridge z platform, które ten procesor obsługują.

Główne źródła porównawcze:

- ASRock **X570 Taichi 2.70** — BIOS docelowy,
- ASRock **X470 Taichi 4.60** — donor zgodny z rodziną ASRock i wspierający Raven Ridge,
- Gigabyte **X570 AORUS F10** — donor używany dla części modułów / implementacji X570,
- dodatkowo porównania z innymi BIOS-ami AM4, m.in. B550, gdy potrzebne jest rozpoznanie konkretnej implementacji DXE.

---

# 1. Punkt wyjścia

Pierwsze wersje modyfikacji dochodziły do:

```text
98
```

Pierwotnie wyglądało to jak problem na etapie PCI / console / device initialization, ale dalsza instrumentacja wykazała, że problem jest znacznie późniejszy i dotyczy przede wszystkim ścieżki:

```text
SataController
    ↓
AHCI DXE
    ↓
inicjalizacja kontrolera / portów
```

Wczesne wersje `v004–v015` miały również problem z pipeline'em modyfikacji — planowany patch DEPEX nie był faktycznie aplikowany.

---

# 2. Ustalony baseline

Za właściwy baseline projektu przyjęta została gałąź:

```text
V86 / V87
```

Najważniejsze cechy:

- `V86` potwierdził poprawne występowanie / znalezienie `EFI_PCI_IO_PROTOCOL`,
- `V87` ma poprawny układ Apriori,
- **NvramDxe pozostaje na pozycji 5**,
- dalsze eksperymenty wykonywane są bez rozwalania tego układu.

To jest obecnie referencyjna baza, od której wykonywane są kolejne instrumentowane buildy.

---

# 3. Etap SataController

Kolejne eksperymenty pozwoliły przejść przez inicjalizację `SataController`.

Istotne wersje:

| Wersja | Wynik / marker | Wniosek |
|---|---:|---|
| `v124B` | `F3 → 4F → 60 → 98 → D5` | wejście głębiej w ścieżkę |
| `v125B` | `D4` | późny etap `PCI_IO` |
| `v125A` | `92` | alternatywna ścieżka niepoprawna |
| `v126B` | `D3 → D6` | późny etap PCD |
| `v126A` | `92` | regresja |
| `v127` | `92`, brak `D3` | niekorzystna zmiana |
| `v129` | `D3` | dobry nowy baseline |
| `v130` | `D9` | `OpenProtocol(PCI_IO, BY_DRIVER)` |
| `v131` | `03` | `EFI_UNSUPPORTED` |
| `v132` | `DA` | wejście w error path |
| `v138` | `E0` | **SataController Start() kończy się poprawnie** |

Kluczowy wynik:

> **SataController przestał być głównym blockerem.**

---

# 4. Problem z dispatchowaniem AHCI

Po uruchomieniu `SataController` AHCI nadal nie był automatycznie dispatchowany.

`v139`:

```text
D4
```

AHCI nie ruszał.

Wprowadzono więc wymuszony układ DXE Apriori.

W `v140`:

```text
slot 4  → SataController
slot 5  → NvramDxe
slot 8  → PciRootBridge
slot 9  → PciBus
slot 10 → AHCI
```

Rezultat:

```text
E1
```

AHCI zaczął być wykonywany.

---

# 5. DEPEX AHCI

Dalsza diagnostyka wykazała:

- `SataController` może zostać poprawnie uruchomiony po zastąpieniu DEPEX,
- oryginalny AHCI ma nadal niespełniony dependency expression.

Do wymuszenia dispatchu użyto DEPEX typu TRUE:

```text
TRUE × 9
AND  × 8
END
```

W `v145` marker:

```text
E7
```

odpowiadał za:

```text
LocateHandleBuffer(
    ByProtocol,
    AHCI_BUS_INIT_PROTOCOL,
    ...
)
```

Wniosek:

> problem nie był już tylko kwestią kolejności dispatchu — należało wejść bezpośrednio w `AHCI.Start()`.

---

# 6. Instrumentacja AHCI.Start()

Przeprowadzona została stopniowa instrumentacja kolejnych miejsc w `AHCI.Start()`.

Potwierdzone punkty:

```text
RVA 0x7AB → przechodzi
RVA 0x7C8 → przechodzi
```

Wersje:

```text
v148 → E9
v149 → EA
```

Następny badany obszar znajdował się w pobliżu:

```text
RVA 0x82C
```

---

# 7. Przejście z markerów diagnostycznych do realnego błędu POST

`v150` i `v151` po przejściu markerów AHCI kończyły się już kodem:

```text
07
```

Kod został zaobserwowany powtarzalnie.

To był ważny przełom: wykonanie zaszło na tyle daleko, że zamiast sztucznego markera diagnostycznego pojawił się realny status błędu generowany przez inicjalizację.

---

# 8. Lokalizacja źródła `07`

Dalsza analiza doprowadziła do helpera wywoływanego przez ścieżkę AHCI.

Badany call chain:

```text
AHCI Start
   ↓
helper 0x2078
   ↓
helper 0x65FC
```

Początkowo istniała możliwość, że:

```text
0x2078
```

otrzymuje inny status, a następnie sam zamienia / maskuje go na:

```text
EFI_DEVICE_ERROR
```

co w dalszej ścieżce kończy się kodem POST `07`.

---

# 9. V155 — `0x65FC` jest bezpośrednim źródłem błędu

W `V155` dodany został probe **bezpośrednio po wywołaniu helpera `0x65FC`**.

Wynik:

```text
0x65FC → EFI_DEVICE_ERROR
```

Wniosek:

> **helper `0x65FC` sam generuje `EFI_DEVICE_ERROR`.**

Czyli:

```text
0x65FC
  ↓
EFI_DEVICE_ERROR
  ↓
0x2078 propaguje błąd
  ↓
AHCI init failure
  ↓
POST 07
```

Można więc wykluczyć hipotezę, że `0x2078` jedynie źle interpretuje lub maskuje poprawny status.

---

# 10. Rozbiór helpera `0x65FC`

Po wejściu do środka `0x65FC` znaleziony został jeden z pierwszych potencjalnych lokalnych error pathów.

Helper składa 64-bitową wartość z dwóch pól struktury per-port:

```text
+0x108
+0x10C
```

czyli logicznie:

```c
value =
    ((uint64_t)*(uint32_t *)(port + 0x10C) << 32) |
               *(uint32_t *)(port + 0x108);
```

Następnie istnieje warunek odpowiadający mniej więcej:

```c
if (value == 0)
    return EFI_DEVICE_ERROR;
```

W assemblerze wartość finalnie trafia do:

```text
RBX
```

więc robocza hipoteza była:

```text
RBX == 0
    ↓
EFI_DEVICE_ERROR
    ↓
POST 07
```

---

# 11. V156 — pierwsza hipoteza obalona

`V156` dostał probe po złożeniu wartości:

```text
port + 0x108
port + 0x10C
```

Rezultat POST:

```text
F2
```

Marker potwierdził, że:

```text
RBX != 0
```

czyli złożona 64-bitowa wartość jest **niezerowa**.

Wniosek:

> **pierwszy lokalny warunek `RBX == 0 → EFI_DEVICE_ERROR` nie jest przyczyną naszego `07`.**

To zawęża problem jeszcze głębiej w `0x65FC`.

---

# 12. Aktualny call chain

Obecny obraz błędu wygląda następująco:

```text
DXE Dispatcher
    │
    ├─ SataController
    │      └─ Start() OK
    │
    └─ AHCI
           │
           └─ Start()
                │
                └─ helper 0x2078
                       │
                       └─ helper 0x65FC
                              │
                              ├─ value(+108/+10C) != 0    ← POTWIERDZONE V156
                              │
                              └─ [kolejny lokalny test]
                                      │
                                      └─ EFI_DEVICE_ERROR
                                             │
                                             └─ POST 07
```

---

# 13. Co zostało już wykluczone

Na obecnym etapie można odrzucić kilka wcześniejszych hipotez.

### Nie jest głównym problemem:

- brak uruchomienia `SataController`,
- sam DXE Apriori,
- pozycja `NvramDxe`,
- brak `EFI_PCI_IO_PROTOCOL`,
- `OpenProtocol()` jako pierwotne źródło obecnego `07`,
- samo niedispatchowanie AHCI,
- maskowanie poprawnego statusu przez helper `0x2078`,
- pierwszy check w `0x65FC`:

```text
RBX == 0
```

dla wartości składanej z:

```text
+0x108 / +0x10C
```

---

# 14. Aktualny blocker

Aktualny blocker znajduje się **wewnątrz helpera `0x65FC`**, po pierwszym sprawdzonym warunku.

Wiemy już:

```text
wejście do 0x65FC                 OK
64-bitowa wartość +108/+10C       != 0
pierwszy error branch             NIE JEST BRANY
...
dalsza część 0x65FC               ???
...
return EFI_DEVICE_ERROR            TAK
```

Trzeba więc znaleźć **następny punkt, z którego helper może zwrócić `EFI_DEVICE_ERROR`**.

---

# 15. Następny krok

Następna wersja diagnostyczna powinna kontynuować binary-search / markerowanie `0x65FC`.

Priorytet:

1. rozebrać cały CFG `0x65FC`,
2. oznaczyć wszystkie bezpośrednie ścieżki prowadzące do:

```text
EFI_DEVICE_ERROR
```

3. znaleźć pierwszy warunek po checku `RBX`,
4. instrumentować **status zaraz po każdym kolejnym callu**, zamiast wyłącznie końcowy return,
5. rozróżniać:
   - lokalny `return EFI_DEVICE_ERROR`,
   - propagację `EFI_ERROR(Status)` z niższego helpera.

Szczególnie interesujące są konstrukcje:

```asm
call    ...
test    rax, rax
js      error
```

oraz:

```asm
cmp     ...
je/jne   device_error
```

i miejsca, które jawnie ustawiają:

```text
0x8000000000000007
```

czyli:

```text
EFI_DEVICE_ERROR
```

---

# 16. Zalecana forma V157

Roboczo:

```text
V157
```

powinien dostać marker **za następnym istotnym basic blockiem w `0x65FC`**, już za potwierdzonym checkiem wartości z `+0x108/+0x10C`.

Nie ma obecnie sensu wracać do:

```text
AHCI.Start
0x2078
SataController
Apriori
DEPEX
```

dopóki nie zostanie zidentyfikowana konkretna ścieżka błędu wewnątrz `0x65FC`.

---

# 17. Najważniejszy stan na dziś

```text
SataController        → OK
AHCI dispatch         → OK
AHCI.Start            → wykonuje się
helper 0x2078         → wykonuje się
helper 0x65FC         → wykonuje się
+108/+10C             → wartość niezerowa
0x65FC                → zwraca EFI_DEVICE_ERROR
POST                  → 07
```

Czyli główny problem projektu jest obecnie zawężony z ogólnego:

> „Athlon 3000G nie przechodzi inicjalizacji na X570 Taichi”

do bardzo konkretnego:

> **„Który wewnętrzny warunek / podrzędny helper w funkcji AHCI `0x65FC` generuje `EFI_DEVICE_ERROR` na Raven Ridge?”**

To jest aktualny punkt startowy do kolejnej sesji.