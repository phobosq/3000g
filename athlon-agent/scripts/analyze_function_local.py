from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.cfg import (
    build_cfg_internal,
    collect_calls,
    collect_status_check_candidates_v3,
    instruction_immediates,
    find_error_value_definitions,
    trace_register_uses,
    EFI_DEVICE_ERROR,
)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "file",
        help="PE/EFI image",
    )

    parser.add_argument(
        "rva",
        help="Function RVA, e.g. 0x65FC",
    )

    parser.add_argument(
        "--max-bytes",
        type=lambda x: int(x, 0),
        default=0x2000,
    )

    parser.add_argument(
        "--output",
        default=None,
    )

    args = parser.parse_args()

    start_rva = int(
        args.rva,
        0,
    )

    cfg = build_cfg_internal(
        args.file,
        start_rva,
        args.max_bytes,
    )

    calls = collect_calls(cfg)

    status_checks = (
        collect_status_check_candidates_v3(
            cfg
        )
    )

    error_definitions = (
        find_error_value_definitions(
            cfg,
            args.file,
        )
    )

    addresses = [
        insn.address
        for block
        in cfg["blocks"].values()
        for insn
        in block.instructions
    ]

    immediates = (
        instruction_immediates(
            args.file,
            addresses,
        )
    )

    error_sites = []

    error_dataflow = []

    for definition in error_definitions:

        reg = definition["destination"]

        if not reg:
            continue

        uses = trace_register_uses(
            cfg,
            reg,
            definition["address"],
            max_forward_bytes=0x400,
        )

        error_dataflow.append({
            "definition": {
                "address": (
                    f"0x{definition['address']:X}"
                ),
                "register": reg,
            },
            "uses": [
                {
                    "address": (
                        f"0x{x['address']:X}"
                    ),
                    "instruction": (
                        f"{x['mnemonic']} "
                        f"{x['operand']}"
                    ),
                }
                for x in uses
            ],
        })

    for block in cfg["blocks"].values():

        for insn in block.instructions:

            values = immediates.get(
                insn.address,
                [],
            )

            if EFI_DEVICE_ERROR in values:

                error_sites.append({
                    "address": (
                        f"0x{insn.address:X}"
                    ),
                    "instruction": (
                        f"{insn.mnemonic} "
                        f"{insn.op_str}"
                    ),
                })

    report = {
        "file": args.file,
        "function_start": (
            f"0x{start_rva:X}"
        ),
        "analysis_range_bytes": (
            f"0x{args.max_bytes:X}"
        ),

        "max_allowed_rva": (
            f"0x{start_rva + args.max_bytes:X}"
        ),        

        "basic_block_count": (
            len(cfg["blocks"])
        ),

        "calls": [
            {
                "site": (
                    f"0x{x['site']:X}"
                ),

                "type": (
                    "direct"
                    if x["target"]
                    is not None
                    else "indirect"
                ),

                "target": (
                    f"0x{x['target']:X}"
                    if x["target"]
                    is not None
                    else None
                ),

                "operand": x["op_str"],
            }
            for x in calls
        ],

        "efi_device_error_sites":
            error_sites,

        "efi_error_definitions": [
            {
                "address": (
                    f"0x{x['address']:X}"
                ),
                "instruction": (
                    f"{x['mnemonic']} "
                    f"{x['operand']}"
                ),
                "destination": (
                    x["destination"]
                ),
            }
            for x in error_definitions
        ],

        "efi_error_dataflow": error_dataflow,

        "status_check_candidates": [
            {
                "call_site":
                    f"0x{x['call'].address:X}",

                "callee":
                    (
                        f"0x{x['call'].target:X}"
                        if x["call"].target
                        is not None
                        else None
                    ),

                "check_site":
                    f"0x{x['check'].address:X}",

                "check":
                    (
                        f"{x['check'].mnemonic} "
                        f"{x['check'].op_str}"
                    ),

                "branch_site":
                    f"0x{x['branch'].address:X}",

                "branch":
                    (
                        f"{x['branch'].mnemonic} "
                        f"{x['branch'].op_str}"
                    ),
            }
            for x
            in status_checks
        ],
    }

    text = json.dumps(
        report,
        indent=2,
    )

    if args.output:

        output = Path(
            args.output
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            text,
            encoding="utf-8",
        )

        print(
            f"written: {output}"
        )

    else:
        print(text)


if __name__ == "__main__":
    main()