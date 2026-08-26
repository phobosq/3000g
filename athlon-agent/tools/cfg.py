from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pefile

from capstone import (
    Cs,
    CS_ARCH_X86,
    CS_MODE_32,
    CS_MODE_64,
    CS_GRP_CALL,
    CS_GRP_JUMP,
    CS_GRP_RET,
)

from capstone.x86_const import X86_OP_IMM

from agents import function_tool

from .common import safe_path


@dataclass
class InstructionInfo:
    address: int
    size: int
    mnemonic: str
    op_str: str
    raw: bytes
    target: Optional[int] = None


@dataclass
class BasicBlock:
    start: int
    instructions: list[InstructionInfo] = field(default_factory=list)
    successors: list[int] = field(default_factory=list)
    terminal_reason: str = ""


def _open_pe(relative_path: str):
    path = safe_path(relative_path)

    if not path.is_file():
        raise ValueError(f"Not a file: {relative_path}")

    try:
        pe = pefile.PE(
            str(path),
            fast_load=False,
        )
    except pefile.PEFormatError as exc:
        raise ValueError(
            f"Invalid PE: {relative_path}: {exc}"
        )

    return path, pe


def _capstone(pe: pefile.PE) -> Cs:
    machine = pe.FILE_HEADER.Machine

    if machine == 0x8664:
        md = Cs(
            CS_ARCH_X86,
            CS_MODE_64,
        )

    elif machine == 0x014C:
        md = Cs(
            CS_ARCH_X86,
            CS_MODE_32,
        )

    else:
        raise ValueError(
            f"Unsupported architecture 0x{machine:04X}"
        )

    md.detail = True

    return md


def _decode_one(
    data: bytes,
    pe: pefile.PE,
    md: Cs,
    rva: int,
) -> Optional[InstructionInfo]:

    try:
        offset = pe.get_offset_from_rva(rva)
    except Exception:
        return None

    if offset >= len(data):
        return None

    chunk = data[
        offset:
        min(offset + 15, len(data))
    ]

    decoded = list(
        md.disasm(
            chunk,
            rva,
            count=1,
        )
    )

    if not decoded:
        return None

    insn = decoded[0]

    target = None

    if getattr(insn, "operands", None):
        first = insn.operands[0]

        if first.type == X86_OP_IMM:
            target = (
                first.imm
                & 0xFFFFFFFFFFFFFFFF
            )

    return InstructionInfo(
        address=insn.address,
        size=insn.size,
        mnemonic=insn.mnemonic.lower(),
        op_str=insn.op_str,
        raw=bytes(insn.bytes),
        target=target,
    )


def _is_unconditional_jump(
    insn: InstructionInfo,
) -> bool:
    return insn.mnemonic == "jmp"


def _is_conditional_jump(
    insn: InstructionInfo,
) -> bool:

    mnemonic = insn.mnemonic

    if mnemonic == "jmp":
        return False

    return mnemonic.startswith("j")


def _is_ret(
    insn: InstructionInfo,
) -> bool:

    return insn.mnemonic.startswith("ret")


def _is_call(
    insn: InstructionInfo,
) -> bool:

    return insn.mnemonic == "call"


def build_cfg_internal(
    relative_path: str,
    start_rva: int,
    max_bytes: int,
) -> dict:

    path, pe = _open_pe(relative_path)

    data = path.read_bytes()

    md = _capstone(pe)

    min_rva = start_rva
    max_rva = start_rva + max_bytes

    pending = [start_rva]
    discovered = set()

    raw_blocks: dict[int, BasicBlock] = {}

    while pending:
        block_start = pending.pop()

        if block_start in discovered:
            continue

        if not (
            min_rva <= block_start < max_rva
        ):
            continue

        discovered.add(block_start)

        block = BasicBlock(
            start=block_start
        )

        current = block_start

        instruction_guard = 0

        while (
            min_rva <= current < max_rva
        ):
            instruction_guard += 1

            if instruction_guard > 4096:
                block.terminal_reason = (
                    "instruction_guard"
                )
                break

            insn = _decode_one(
                data,
                pe,
                md,
                current,
            )

            if insn is None:
                block.terminal_reason = (
                    "decode_failure"
                )
                break

            block.instructions.append(insn)

            next_rva = (
                insn.address
                + insn.size
            )

            if _is_ret(insn):
                block.terminal_reason = "ret"
                break

            if _is_unconditional_jump(insn):

                if insn.target is not None:
                    block.successors.append(
                        insn.target
                    )

                    if (
                        min_rva
                        <= insn.target
                        < max_rva
                    ):
                        pending.append(
                            insn.target
                        )

                    block.terminal_reason = (
                        "direct_jmp"
                    )

                else:
                    block.terminal_reason = (
                        "indirect_jmp"
                    )

                break

            if _is_conditional_jump(insn):

                if insn.target is not None:
                    block.successors.append(
                        insn.target
                    )

                    if (
                        min_rva
                        <= insn.target
                        < max_rva
                    ):
                        pending.append(
                            insn.target
                        )

                block.successors.append(
                    next_rva
                )

                if (
                    min_rva
                    <= next_rva
                    < max_rva
                ):
                    pending.append(
                        next_rva
                    )

                block.terminal_reason = (
                    "conditional_jump"
                )

                break

            # Calls do NOT terminate a block.
            # We deliberately do not follow callees.

            current = next_rva

        raw_blocks[
            block_start
        ] = block

    cfg = {
        "start_rva": start_rva,
        "max_rva": max_rva,
        "blocks": raw_blocks,
    }

    return normalize_blocks(cfg)


def normalize_blocks(
    cfg: dict,
) -> dict:

    blocks: dict[int, BasicBlock] = (
        cfg["blocks"]
    )

    branch_targets = set()

    for block in blocks.values():
        for target in block.successors:
            branch_targets.add(target)

    result: dict[int, BasicBlock] = {}

    for block in blocks.values():

        split_points = sorted(
            target
            for target in branch_targets
            if (
                target != block.start
                and any(
                    insn.address == target
                    for insn
                    in block.instructions
                )
            )
        )

        if not split_points:
            result[
                block.start
            ] = block

            continue

        current_instructions = []

        for insn in block.instructions:

            if (
                insn.address in split_points
                and current_instructions
            ):

                new_block = BasicBlock(
                    start=
                    current_instructions[0].address,
                    instructions=
                    current_instructions,
                    successors=[
                        insn.address
                    ],
                    terminal_reason=
                    "split_fallthrough",
                )

                result[
                    new_block.start
                ] = new_block

                current_instructions = []

            current_instructions.append(
                insn
            )

        if current_instructions:

            new_block = BasicBlock(
                start=
                current_instructions[0].address,
                instructions=
                current_instructions,
                successors=
                block.successors,
                terminal_reason=
                block.terminal_reason,
            )

            result[
                new_block.start
            ] = new_block

    cfg = dict(cfg)
    cfg["blocks"] = result

    return cfg


def format_cfg(cfg: dict) -> str:

    blocks: dict[int, BasicBlock] = (
        cfg["blocks"]
    )

    lines = []

    lines.append(
        f"function_start=0x{cfg['start_rva']:X}"
    )

    lines.append(
        f"analysis_limit=0x{cfg['max_rva']:X}"
    )

    lines.append(
        f"basic_blocks={len(blocks)}"
    )

    lines.append("")

    for start in sorted(blocks):

        block = blocks[start]

        lines.append(
            f"BLOCK 0x{start:X}"
        )

        for insn in block.instructions:

            raw = " ".join(
                f"{b:02X}"
                for b in insn.raw
            )

            lines.append(
                f"  {insn.address:08X} "
                f"{raw:<30} "
                f"{insn.mnemonic:<8} "
                f"{insn.op_str}"
            )

        successors = ", ".join(
            f"0x{x:X}"
            for x in block.successors
        )

        lines.append(
            f"  successors: "
            f"{successors or '-'}"
        )

        lines.append(
            f"  terminator: "
            f"{block.terminal_reason}"
        )

        lines.append("")

    return "\n".join(lines)


@function_tool
def build_function_cfg(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
) -> str:
    """
    Build a recursive control-flow graph for a function.

    Calls are recorded but not followed into callees.

    Args:
        relative_path:
            PE/EFI file relative to project root.

        start_rva:
            Function start RVA.

        max_bytes:
            Maximum RVA range considered part of the
            current function analysis.
    """

    if max_bytes < 64:
        raise ValueError(
            "max_bytes too small"
        )

    if max_bytes > 65536:
        raise ValueError(
            "max_bytes too large"
        )

    cfg = build_cfg_internal(
        relative_path,
        start_rva,
        max_bytes,
    )

    return format_cfg(cfg)


def collect_calls(
    cfg: dict,
) -> list[dict]:

    calls = []

    for block in cfg["blocks"].values():

        for insn in block.instructions:

            if not _is_call(insn):
                continue

            calls.append({
                "site": insn.address,
                "target": insn.target,
                "op_str": insn.op_str,
            })

    return calls


@function_tool
def list_function_calls(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
) -> str:
    """
    List calls reachable from a function entry.
    """

    cfg = build_cfg_internal(
        relative_path,
        start_rva,
        max_bytes,
    )

    calls = collect_calls(cfg)

    if not calls:
        return "No reachable calls found."

    lines = []

    for call in calls:

        if call["target"] is None:
            target = (
                f"indirect ({call['op_str']})"
            )
        else:
            target = (
                f"0x{call['target']:X}"
            )

        lines.append(
            f"0x{call['site']:X}"
            f" -> {target}"
        )

    return "\n".join(lines)


EFI_DEVICE_ERROR = (
    0x8000000000000007
)


def instruction_immediates(
    relative_path: str,
    addresses: list[int],
) -> dict[int, list[int]]:

    path, pe = _open_pe(
        relative_path
    )

    data = path.read_bytes()

    md = _capstone(pe)

    result = {}

    for address in addresses:

        try:
            offset = (
                pe.get_offset_from_rva(
                    address
                )
            )
        except Exception:
            continue

        insns = list(
            md.disasm(
                data[
                    offset:
                    offset + 15
                ],
                address,
                count=1,
            )
        )

        if not insns:
            continue

        insn = insns[0]

        values = []

        for operand in getattr(
            insn,
            "operands",
            [],
        ):

            if operand.type == X86_OP_IMM:

                values.append(
                    operand.imm
                    & 0xFFFFFFFFFFFFFFFF
                )

        result[address] = values

    return result


@function_tool
def find_cfg_efi_device_error_sites(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
) -> str:
    """
    Find reachable instructions in a function CFG that
    contain EFI_DEVICE_ERROR as an immediate.
    """

    cfg = build_cfg_internal(
        relative_path,
        start_rva,
        max_bytes,
    )

    addresses = []

    for block in cfg["blocks"].values():
        for insn in block.instructions:
            addresses.append(
                insn.address
            )

    immediates = (
        instruction_immediates(
            relative_path,
            addresses,
        )
    )

    hits = []

    for block in cfg["blocks"].values():

        for insn in block.instructions:

            values = immediates.get(
                insn.address,
                [],
            )

            if EFI_DEVICE_ERROR not in values:
                continue

            hits.append(
                f"0x{insn.address:X}: "
                f"{insn.mnemonic} "
                f"{insn.op_str}"
            )

    if not hits:
        return (
            "No reachable direct "
            "EFI_DEVICE_ERROR immediate."
        )

    return "\n".join(hits)


STATUS_REGISTERS = {
    "rax",
    "eax",
}


def looks_like_status_check(
    insn: InstructionInfo,
) -> bool:

    text = (
        f"{insn.mnemonic} "
        f"{insn.op_str}"
    ).lower()

    if not any(
        reg in text
        for reg in STATUS_REGISTERS
    ):
        return False

    return insn.mnemonic in {
        "test",
        "cmp",
        "or",
    }


def collect_status_check_candidates(
    cfg: dict,
) -> list[dict]:

    candidates = []

    for block in cfg["blocks"].values():

        insns = block.instructions

        for i, insn in enumerate(insns):

            if not _is_call(insn):
                continue

            window = insns[
                i + 1:
                i + 8
            ]

            check = None
            branch = None

            for item in window:

                if (
                    check is None
                    and looks_like_status_check(
                        item
                    )
                ):
                    check = item
                    continue

                if (
                    check is not None
                    and _is_conditional_jump(
                        item
                    )
                ):
                    branch = item
                    break

            if (
                check is not None
                and branch is not None
            ):

                candidates.append({
                    "call": insn,
                    "check": check,
                    "branch": branch,
                })

    return candidates


@function_tool
def find_cfg_status_checks(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
) -> str:
    """
    Find reachable calls followed by likely return-status
    checks inside the same basic block.
    """

    cfg = build_cfg_internal(
        relative_path,
        start_rva,
        max_bytes,
    )

    candidates = (
        collect_status_check_candidates(
            cfg
        )
    )

    if not candidates:
        return (
            "No obvious call/status checks."
        )

    lines = []

    for c in candidates:

        call = c["call"]
        check = c["check"]
        branch = c["branch"]

        target = (
            f"0x{call.target:X}"
            if call.target is not None
            else call.op_str
        )

        lines.extend([
            (
                f"call_site=0x"
                f"{call.address:X}"
            ),
            (
                f"callee={target}"
            ),
            (
                f"check=0x"
                f"{check.address:X}: "
                f"{check.mnemonic} "
                f"{check.op_str}"
            ),
            (
                f"branch=0x"
                f"{branch.address:X}: "
                f"{branch.mnemonic} "
                f"{branch.op_str}"
            ),
            "",
        ])

    return "\n".join(lines)


def reachable_instruction_map(
    cfg: dict,
) -> dict[int, InstructionInfo]:

    result = {}

    for block in cfg["blocks"].values():
        for insn in block.instructions:
            result[insn.address] = insn

    return result


def collect_status_check_candidates_v3(
    cfg: dict,
    max_forward_bytes: int = 128,
) -> list[dict]:

    candidates = []

    instruction_map = reachable_instruction_map(cfg)

    addresses = sorted(
        instruction_map.keys()
    )

    index_by_address = {
        address: index
        for index, address
        in enumerate(addresses)
    }

    for address in addresses:

        call = instruction_map[address]

        if not _is_call(call):
            continue

        start_index = (
            index_by_address[address]
            + 1
        )

        check = None
        branch = None

        for j in range(
            start_index,
            len(addresses),
        ):
            current_address = addresses[j]

            if (
                current_address
                - call.address
                > max_forward_bytes
            ):
                break

            insn = instruction_map[
                current_address
            ]

            mnemonic = insn.mnemonic.lower()
            operands = insn.op_str.lower()

            # Possible EFI_STATUS check
            if (
                mnemonic in {
                    "test",
                    "cmp",
                    "or",
                }
                and (
                    "rax" in operands
                    or "eax" in operands
                )
            ):
                check = insn

                for k in range(
                    j + 1,
                    min(
                        j + 5,
                        len(addresses),
                    ),
                ):
                    next_insn = instruction_map[
                        addresses[k]
                    ]

                    if _is_conditional_jump(
                        next_insn
                    ):
                        branch = next_insn
                        break

                break

            # Stop if return register is clobbered
            first_operand = (
                operands
                .split(",", 1)[0]
                .strip()
            )

            if (
                first_operand in {
                    "rax",
                    "eax",
                }
                and mnemonic in {
                    "mov",
                    "lea",
                    "xor",
                    "pop",
                    "and",
                    "or",
                    "add",
                    "sub",
                }
            ):
                break

            # Another call normally clobbers RAX
            if _is_call(insn):
                break

        if (
            check is not None
            and branch is not None
        ):
            candidates.append({
                "call": call,
                "check": check,
                "branch": branch,
            })

    return candidates


def find_error_value_definitions(
    cfg: dict,
    relative_path: str,
) -> list[dict]:

    addresses = []

    for block in cfg["blocks"].values():
        for insn in block.instructions:
            addresses.append(insn.address)

    immediates = instruction_immediates(
        relative_path,
        addresses,
    )

    definitions = []

    for block in cfg["blocks"].values():

        for insn in block.instructions:

            values = immediates.get(
                insn.address,
                [],
            )

            if EFI_DEVICE_ERROR not in values:
                continue

            destination = None

            if "," in insn.op_str:
                destination = (
                    insn.op_str
                    .split(",", 1)[0]
                    .strip()
                    .lower()
                )

            definitions.append({
                "address": insn.address,
                "mnemonic": insn.mnemonic,
                "operand": insn.op_str,
                "destination": destination,
            })

    return definitions


def trace_register_uses(
    cfg: dict,
    source_register: str,
    start_address: int,
    max_forward_bytes: int = 512,
) -> list[dict]:

    instruction_map = (
        reachable_instruction_map(cfg)
    )

    addresses = sorted(
        instruction_map.keys()
    )

    results = []

    for address in addresses:

        if address <= start_address:
            continue

        if (
            address - start_address
            > max_forward_bytes
        ):
            break

        insn = instruction_map[address]

        text = insn.op_str.lower()

        if source_register not in text:
            continue

        results.append({
            "address": insn.address,
            "mnemonic": insn.mnemonic,
            "operand": insn.op_str,
        })

    return results


def build_call_graph(
    relative_path: str,
    start_rva: int,
    depth: int = 2,
    max_bytes_per_function: int = 0x2000,
) -> dict:

    visited = set()

    def walk(function_rva: int, level: int):

        if function_rva in visited:
            return {
                "function": f"0x{function_rva:X}",
                "recursive": True,
            }

        visited.add(function_rva)

        cfg = build_cfg_internal(
            relative_path,
            function_rva,
            max_bytes_per_function,
        )

        calls = collect_calls(cfg)

        node = {
            "function": f"0x{function_rva:X}",
            "calls": [],
        }

        if level >= depth:
            return node

        for call in calls:

            if call["target"] is None:
                node["calls"].append({
                    "site": f"0x{call['site']:X}",
                    "type": "indirect",
                })
                continue

            child = walk(
                call["target"],
                level + 1,
            )

            node["calls"].append({
                "site": f"0x{call['site']:X}",
                "type": "direct",
                "target": child,
            })

        return node

    return walk(
        start_rva,
        0,
    )