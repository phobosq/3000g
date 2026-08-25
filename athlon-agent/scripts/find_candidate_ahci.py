from pathlib import Path
import sys

import pefile
from capstone import (
    Cs,
    CS_ARCH_X86,
    CS_MODE_64,
)


TARGET_RVA = 0x65FC


def main():
    if len(sys.argv) != 2:
        print("usage: find_candidate_ahci.py <extract-directory>")
        raise SystemExit(1)

    root = Path(sys.argv[1])

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        try:
            with path.open("rb") as f:
                if f.read(2) != b"MZ":
                    continue

            pe = pefile.PE(str(path))

            if pe.FILE_HEADER.Machine != 0x8664:
                continue

            if pe.OPTIONAL_HEADER.SizeOfImage <= TARGET_RVA:
                continue

            try:
                raw = pe.get_offset_from_rva(
                    TARGET_RVA
                )
            except Exception:
                continue

            data = path.read_bytes()

            if raw >= len(data):
                continue

            code = data[
                raw:
                raw + 64
            ]

            md = Cs(
                CS_ARCH_X86,
                CS_MODE_64,
            )

            insns = list(
                md.disasm(
                    code,
                    TARGET_RVA,
                )
            )

            if len(insns) < 5:
                continue

            print()
            print("=" * 80)
            print(path)
            print(
                f"size={path.stat().st_size} "
                f"image=0x{pe.OPTIONAL_HEADER.SizeOfImage:X} "
                f"entry=0x{pe.OPTIONAL_HEADER.AddressOfEntryPoint:X}"
            )

            for insn in insns[:12]:
                print(
                    f"{insn.address:08X}  "
                    f"{insn.mnemonic:<8} "
                    f"{insn.op_str}"
                )

        except Exception:
            pass


if __name__ == "__main__":
    main()