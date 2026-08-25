from __future__ import annotations

from pathlib import Path
from typing import Optional

import pefile

from capstone import (
    Cs,
    CS_ARCH_X86,
    CS_MODE_32,
    CS_MODE_64,
)

from capstone.x86 import *
from capstone.x86_const import X86_OP_IMM

from agents import function_tool

from .common import safe_path


EFI_DEVICE_ERROR = 0x8000000000000007


def _open_pe(relative_path: str) -> tuple[Path, pefile.PE]:
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
            f"File is not a valid PE image: {relative_path}: {exc}"
        )

    return path, pe


def _machine_name(machine: int) -> str:
    names = {
        0x014C: "I386",
        0x8664: "AMD64",
        0xAA64: "ARM64",
    }

    return names.get(
        machine,
        f"UNKNOWN_0x{machine:04X}",
    )


def _section_name(section) -> str:
    return (
        section.Name
        .rstrip(b"\x00")
        .decode("ascii", errors="replace")
    )


@function_tool
def inspect_pe(relative_path: str) -> str:
    """
    Inspect a PE/COFF executable such as a UEFI PE32 or PE32+ image.

    Args:
        relative_path:
            File path relative to the project root,
            for example analysis/ahci_v156/AhciDxe.efi.
    """

    path, pe = _open_pe(relative_path)

    machine = pe.FILE_HEADER.Machine
    image_base = pe.OPTIONAL_HEADER.ImageBase
    entry_rva = pe.OPTIONAL_HEADER.AddressOfEntryPoint
    image_size = pe.OPTIONAL_HEADER.SizeOfImage

    lines = [
        f"path={relative_path}",
        f"size={path.stat().st_size}",
        f"machine={_machine_name(machine)}",
        f"machine_raw=0x{machine:04X}",
        f"image_base=0x{image_base:X}",
        f"entry_rva=0x{entry_rva:X}",
        f"entry_va=0x{image_base + entry_rva:X}",
        f"size_of_image=0x{image_size:X}",
        "",
        "sections:",
    ]

    for section in pe.sections:
        name = _section_name(section)

        lines.append(
            f"  {name:<8} "
            f"RVA=0x{section.VirtualAddress:08X} "
            f"VSIZE=0x{section.Misc_VirtualSize:08X} "
            f"RAW=0x{section.PointerToRawData:08X} "
            f"RAWSIZE=0x{section.SizeOfRawData:08X} "
            f"CHAR=0x{section.Characteristics:08X}"
        )

    return "\n".join(lines)


@function_tool
def rva_to_file_offset(
    relative_path: str,
    rva: int,
) -> str:
    """
    Convert a PE image RVA into a raw file offset.

    Args:
        relative_path:
            PE/EFI file relative to the project root.

        rva:
            Relative virtual address expressed as a decimal integer.
            For RVA 0x65FC pass 26108.
    """

    _, pe = _open_pe(relative_path)

    try:
        offset = pe.get_offset_from_rva(rva)
    except Exception as exc:
        return (
            f"Unable to map RVA 0x{rva:X}: "
            f"{type(exc).__name__}: {exc}"
        )

    containing_section = None

    for section in pe.sections:
        start = section.VirtualAddress

        size = max(
            section.Misc_VirtualSize,
            section.SizeOfRawData,
        )

        if start <= rva < start + size:
            containing_section = _section_name(section)
            break

    return (
        f"rva=0x{rva:X}\n"
        f"file_offset=0x{offset:X}\n"
        f"section={containing_section or 'unknown'}"
    )


def _capstone_for_pe(pe: pefile.PE) -> Cs:
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
            f"Unsupported PE machine: 0x{machine:04X}"
        )

    md.detail = True

    return md


@function_tool
def disassemble_function(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 512,
    max_instructions: int = 200,
) -> str:
    """
    Disassemble machine code beginning at a PE RVA.

    This tool does not attempt to determine the true function boundary.
    It performs linear disassembly beginning at start_rva.

    Args:
        relative_path:
            PE/EFI image relative to project root.

        start_rva:
            RVA where disassembly starts.

        max_bytes:
            Maximum number of bytes to decode.
            Allowed range: 16..4096.

        max_instructions:
            Maximum number of instructions returned.
            Allowed range: 1..1000.
    """

    if max_bytes < 16 or max_bytes > 4096:
        raise ValueError(
            "max_bytes must be between 16 and 4096"
        )

    if max_instructions < 1 or max_instructions > 1000:
        raise ValueError(
            "max_instructions must be between 1 and 1000"
        )

    path, pe = _open_pe(relative_path)

    try:
        raw_offset = pe.get_offset_from_rva(start_rva)
    except Exception as exc:
        raise ValueError(
            f"Cannot map RVA 0x{start_rva:X}: {exc}"
        )

    file_data = path.read_bytes()

    if raw_offset >= len(file_data):
        raise ValueError(
            f"Mapped file offset 0x{raw_offset:X} "
            f"is outside the file"
        )

    code = file_data[
        raw_offset:
        raw_offset + max_bytes
    ]

    md = _capstone_for_pe(pe)

    instructions = list(
        md.disasm(
            code,
            start_rva,
        )
    )

    if not instructions:
        return (
            f"No instructions decoded at RVA "
            f"0x{start_rva:X}"
        )

    lines = [
        f"file={relative_path}",
        f"start_rva=0x{start_rva:X}",
        f"file_offset=0x{raw_offset:X}",
        f"decoded_bytes=0x{len(code):X}",
        "",
    ]

    for index, insn in enumerate(instructions):
        if index >= max_instructions:
            lines.append(
                "... instruction limit reached ..."
            )
            break

        raw = " ".join(
            f"{b:02X}"
            for b in insn.bytes
        )

        lines.append(
            f"{insn.address:08X}  "
            f"{raw:<32} "
            f"{insn.mnemonic:<8} "
            f"{insn.op_str}"
        )

    return "\n".join(lines)


def _is_conditional_jump(insn) -> bool:
    mnemonic = insn.mnemonic.lower()

    if mnemonic == "jmp":
        return False

    return mnemonic.startswith("j")


def _direct_target(insn) -> Optional[int]:
    """
    Return immediate branch/call target if Capstone decoded
    the operand as an immediate value.
    """

    if not getattr(insn, "operands", None):
        return None

    operand = insn.operands[0]

    if operand.type == X86_OP_IMM:
        return operand.imm

    return None


@function_tool
def analyze_control_transfers(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 1024,
) -> str:
    """
    Analyze calls and branches in a PE code range.

    Args:
        relative_path:
            PE/EFI image relative to project root.

        start_rva:
            RVA at which analysis begins.

        max_bytes:
            Number of bytes to inspect.
            Allowed range: 16..8192.
    """

    if max_bytes < 16 or max_bytes > 8192:
        raise ValueError(
            "max_bytes must be between 16 and 8192"
        )

    path, pe = _open_pe(relative_path)

    raw_offset = pe.get_offset_from_rva(start_rva)

    data = path.read_bytes()[
        raw_offset:
        raw_offset + max_bytes
    ]

    md = _capstone_for_pe(pe)

    results = []

    for insn in md.disasm(
        data,
        start_rva,
    ):
        mnemonic = insn.mnemonic.lower()

        interesting = (
            mnemonic == "call"
            or mnemonic == "jmp"
            or _is_conditional_jump(insn)
            or mnemonic == "ret"
        )

        if not interesting:
            continue

        target = _direct_target(insn)

        if target is None:
            target_text = ""
        else:
            target_text = f" -> 0x{target:X}"

        results.append(
            f"0x{insn.address:08X}: "
            f"{insn.mnemonic} {insn.op_str}"
            f"{target_text}"
        )

    if not results:
        return "No control-transfer instructions found"

    return "\n".join(results)


@function_tool
def find_efi_device_error_immediates(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
) -> str:
    """
    Look for instructions containing the immediate value
    EFI_DEVICE_ERROR = 0x8000000000000007.

    Args:
        relative_path:
            PE/EFI image relative to project root.

        start_rva:
            RVA at which scanning begins.

        max_bytes:
            Number of bytes to scan.
            Allowed range: 16..16384.
    """

    if max_bytes < 16 or max_bytes > 16384:
        raise ValueError(
            "max_bytes must be between 16 and 16384"
        )

    path, pe = _open_pe(relative_path)

    raw_offset = pe.get_offset_from_rva(start_rva)

    data = path.read_bytes()[
        raw_offset:
        raw_offset + max_bytes
    ]

    md = _capstone_for_pe(pe)

    hits = []

    for insn in md.disasm(
        data,
        start_rva,
    ):
        for operand in getattr(insn, "operands", []):
            if operand.type != X86_OP_IMM:
                continue

            value = operand.imm & 0xFFFFFFFFFFFFFFFF

            if value == EFI_DEVICE_ERROR:
                raw = " ".join(
                    f"{b:02X}"
                    for b in insn.bytes
                )

                hits.append(
                    f"0x{insn.address:08X}  "
                    f"{raw:<32} "
                    f"{insn.mnemonic} {insn.op_str}"
                )

    if not hits:
        return (
            "No direct EFI_DEVICE_ERROR "
            "immediates found in the decoded range."
        )

    return "\n".join(hits)


@function_tool
def find_call_status_checks(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
) -> str:
    """
    Find calls followed shortly by instructions that may test
    an EFI_STATUS result.

    This is heuristic analysis. A reported sequence is a candidate,
    not proof that the call returns EFI_STATUS.

    Args:
        relative_path:
            PE/EFI image relative to project root.

        start_rva:
            RVA where scanning begins.

        max_bytes:
            Number of bytes to inspect.
            Allowed range: 32..16384.
    """

    if max_bytes < 32 or max_bytes > 16384:
        raise ValueError(
            "max_bytes must be between 32 and 16384"
        )

    path, pe = _open_pe(relative_path)

    raw_offset = pe.get_offset_from_rva(start_rva)

    data = path.read_bytes()[
        raw_offset:
        raw_offset + max_bytes
    ]

    md = _capstone_for_pe(pe)

    instructions = list(
        md.disasm(
            data,
            start_rva,
        )
    )

    hits = []

    interesting_checks = {
        "test",
        "cmp",
        "or",
    }

    interesting_branches = {
        "js",
        "jns",
        "jl",
        "jge",
        "je",
        "jne",
        "jz",
        "jnz",
    }

    for i, insn in enumerate(instructions):
        if insn.mnemonic.lower() != "call":
            continue

        window = instructions[
            i:
            min(i + 7, len(instructions))
        ]

        has_check = False
        has_branch = False

        for item in window[1:]:
            mnemonic = item.mnemonic.lower()

            if mnemonic in interesting_checks:
                has_check = True

            if mnemonic in interesting_branches:
                has_branch = True

        if not (has_check and has_branch):
            continue

        hits.append(
            f"\nCandidate after call at "
            f"0x{insn.address:X}:"
        )

        for item in window:
            raw = " ".join(
                f"{b:02X}"
                for b in item.bytes
            )

            hits.append(
                f"  {item.address:08X}  "
                f"{raw:<30} "
                f"{item.mnemonic:<7} "
                f"{item.op_str}"
            )

    if not hits:
        return (
            "No obvious call/status-check "
            "sequences found."
        )

    return "\n".join(hits)