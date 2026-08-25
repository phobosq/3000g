from pathlib import Path
import sys
import pefile


def main():
    if len(sys.argv) != 2:
        print("usage: find_pe_images.py <directory>")
        raise SystemExit(1)

    root = Path(sys.argv[1])

    if not root.is_dir():
        print(f"not a directory: {root}")
        raise SystemExit(1)

    hits = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        try:
            with path.open("rb") as f:
                if f.read(2) != b"MZ":
                    continue

            pe = pefile.PE(
                str(path),
                fast_load=True,
            )

            hits.append(
                (
                    path.stat().st_size,
                    pe.FILE_HEADER.Machine,
                    pe.OPTIONAL_HEADER.AddressOfEntryPoint,
                    path,
                )
            )

        except Exception:
            continue

    hits.sort()

    for size, machine, entry, path in hits:
        arch = {
            0x8664: "AMD64",
            0x014C: "I386",
        }.get(
            machine,
            f"0x{machine:04X}",
        )

        print(
            f"{size:8d}  "
            f"{arch:8}  "
            f"entry=0x{entry:06X}  "
            f"{path}"
        )


if __name__ == "__main__":
    main()