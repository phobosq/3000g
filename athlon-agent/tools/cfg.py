from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from copy import deepcopy

import pefile
import re

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

CMOV_CONDITIONS = {
    "cmove": "e",
    "cmovz": "z",

    "cmovne": "ne",
    "cmovnz": "nz",
}


class SymbolKind(str, Enum):
    UNKNOWN = "UNKNOWN"
    EFI_DEVICE_ERROR = "EFI_DEVICE_ERROR"
    ZERO = "ZERO"
    FROM_CALL = "FROM_CALL"
    CONSTANT = "CONSTANT"


@dataclass(frozen=True)
class SymbolicValue:
    kind: SymbolKind
    detail: str | None = None
    origin: int | None = None

    def __str__(self):
        if self.detail is None:
            return self.kind.value

        return f"{self.kind.value}({self.detail})"

UNKNOWN = SymbolicValue(
    SymbolKind.UNKNOWN
)

EFI_DEVICE_ERROR_VALUE = SymbolicValue(
    SymbolKind.EFI_DEVICE_ERROR
)

ZERO_VALUE = SymbolicValue(
    SymbolKind.ZERO
)


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

    instructions: list[
        InstructionInfo
    ] = field(
        default_factory=list
    )

    successors: list[int] = field(
        default_factory=list
    )

    terminal_reason: str = ""

    edges: list[
        CFGEdge
    ] = field(
        default_factory=list
    )


@dataclass
class CFGEdge:
    target: int
    kind: str
    condition_code: str | None = None
    

@dataclass
class SymbolicState:
    registers: dict[
        str,
        SymbolicValue
    ] = field(default_factory=dict)

    stack_slots: dict[
        str,
        SymbolicValue
    ] = field(default_factory=dict)

    flags_source: FlagSource | None = None

    path: list[int] = field(
        default_factory=list
    )

    notes: list[str] = field(
        default_factory=list
    )

    block_visits: dict[
        int,
        int
    ] = field(
        default_factory=dict
    )

    conditions: list[str] = field(
        default_factory=list
    )

    path_conditions: list[str] = field(
        default_factory=list
    )

    def clone(self):
        return deepcopy(self)

    def get_reg(
        self,
        reg: str,
    ) -> SymbolicValue:
        return self.registers.get(
            canonical_register(reg),
            UNKNOWN,
        )

    def set_reg(
        self,
        reg: str,
        value: SymbolicValue,
    ):

        canonical = canonical_register(
            reg
        )

        invalidate_conditions_for_register(
            self,
            canonical,
        )

        self.registers[
            canonical
        ] = value


@dataclass(frozen=True)
class FlagSource:
    address: int
    mnemonic: str
    operands: str

    def __str__(self):
        return (
            f"0x{self.address:X}: "
            f"{self.mnemonic} "
            f"{self.operands}"
        )

        
REGISTER_ALIASES = {
    "rax": "rax",
    "eax": "rax",
    "ax": "rax",
    "al": "rax",
    "ah": "rax",

    "rbx": "rbx",
    "ebx": "rbx",
    "bx": "rbx",
    "bl": "rbx",
    "bh": "rbx",

    "rcx": "rcx",
    "ecx": "rcx",
    "cx": "rcx",
    "cl": "rcx",
    "ch": "rcx",

    "rdx": "rdx",
    "edx": "rdx",
    "dx": "rdx",
    "dl": "rdx",
    "dh": "rdx",

    "rsi": "rsi",
    "esi": "rsi",
    "si": "rsi",
    "sil": "rsi",

    "rdi": "rdi",
    "edi": "rdi",
    "di": "rdi",
    "dil": "rdi",

    "r12": "r12",
    "r12d": "r12",
    "r12w": "r12",
    "r12b": "r12",

    "r13": "r13",
    "r13d": "r13",
    "r13w": "r13",
    "r13b": "r13",

    "r14": "r14",
    "r14d": "r14",
    "r14w": "r14",
    "r14b": "r14",

    "r15": "r15",
    "r15d": "r15",
    "r15w": "r15",
    "r15b": "r15",

    "rbp": "rbp",
    "ebp": "rbp",
    "bp": "rbp",
    "bpl": "rbp",

    "rsp": "rsp",
    "esp": "rsp",
    "sp": "rsp",
    "spl": "rsp",

    "r8": "r8",
    "r8d": "r8",
    "r8w": "r8",
    "r8b": "r8",

    "r9": "r9",
    "r9d": "r9",
    "r9w": "r9",
    "r9b": "r9",

    "r10": "r10",
    "r10d": "r10",
    "r10w": "r10",
    "r10b": "r10",

    "r11": "r11",
    "r11d": "r11",
    "r11w": "r11",
    "r11b": "r11",    
}


JCC_CONDITIONS = {
    "je": "e",
    "jz": "z",

    "jne": "ne",
    "jnz": "nz",

    "js": "s",
    "jns": "ns",

    "jb": "b",
    "jc": "b",
    "jnae": "b",

    "jae": "ae",
    "jnb": "ae",
    "jnc": "ae",

    "jbe": "be",
    "jna": "be",

    "ja": "a",
    "jnbe": "a",

    "jl": "l",
    "jnge": "l",

    "jge": "ge",
    "jnl": "ge",

    "jle": "le",
    "jng": "le",

    "jg": "g",
    "jnle": "g",
}


OPPOSITE_CONDITION = {
    "e": "ne",
    "z": "nz",

    "ne": "e",
    "nz": "z",

    "s": "ns",
    "ns": "s",

    "b": "ae",
    "ae": "b",

    "be": "a",
    "a": "be",

    "l": "ge",
    "ge": "l",

    "le": "g",
    "g": "le",
}


def canonical_register(
    register: str,
) -> str:
    return REGISTER_ALIASES.get(
        register.lower(),
        register.lower(),
    )


def condition_registers(
    condition: str,
) -> set[str]:

    tokens = re.findall(
        r"\b[a-zA-Z][a-zA-Z0-9]*\b",
        condition,
    )

    result = set()

    for token in tokens:

        token = token.lower()

        if token not in REGISTER_ALIASES:
            continue

        result.add(
            canonical_register(token)
        )

    return result


def invalidate_conditions_for_register(
    state: SymbolicState,
    register: str,
):

    register = canonical_register(
        register
    )

    state.conditions = [
        condition
        for condition in state.conditions
        if (
            register
            not in condition_registers(
                condition
            )
        )
    ]


def split_operands(
    op_str: str,
) -> list[str]:
    if not op_str:
        return []

    return [
        x.strip().lower()
        for x in op_str.split(",")
    ]


def is_register_operand(
    operand: str,
) -> bool:
    return operand in REGISTER_ALIASES


def parse_immediate(
    operand: str,
) -> int | None:

    operand = operand.strip().lower()

    try:
        return int(
            operand,
            0,
        )
    except ValueError:
        return None
    

def apply_mov(
    state: SymbolicState,
    insn: InstructionInfo,
):

    operands = split_operands(
        insn.op_str
    )

    if len(operands) != 2:
        return

    dst, src = operands

    dst_stack = normalize_stack_slot(
        dst
    )

    src_stack = normalize_stack_slot(
        src
    )

    # stack <- register
    if (
        dst_stack is not None
        and is_register_operand(src)
    ):
        value = state.get_reg(src)

        state.stack_slots[
            dst_stack
        ] = value

        state.notes.append(
            f"0x{insn.address:X}: "
            f"{dst_stack} <- {value}"
        )

        return

    # register <- stack
    if (
        is_register_operand(dst)
        and src_stack is not None
    ):
        value = state.stack_slots.get(
            src_stack,
            UNKNOWN,
        )

        state.set_reg(
            dst,
            value,
        )

        state.notes.append(
            f"0x{insn.address:X}: "
            f"{canonical_register(dst)} "
            f"<- {value} "
            f"from {src_stack}"
        )

        return

    if not is_register_operand(dst):
        return

    # register <- register
    if is_register_operand(src):

        value = state.get_reg(src)

        state.set_reg(
            dst,
            value,
        )

        if value.kind != SymbolKind.UNKNOWN:
            state.notes.append(
                f"0x{insn.address:X}: "
                f"{canonical_register(dst)} "
                f"<- {value} "
                f"from {canonical_register(src)}"
            )

        return

    # register <- immediate
    immediate = parse_immediate(src)

    if immediate is not None:

        immediate &= (
            0xFFFFFFFFFFFFFFFF
        )

        if immediate == 0:
            value = ZERO_VALUE

        elif immediate == EFI_DEVICE_ERROR:

            value = SymbolicValue(
                SymbolKind.EFI_DEVICE_ERROR,
                origin=insn.address,
            )

        else:
            value = SymbolicValue(
                SymbolKind.CONSTANT,
                f"0x{immediate:X}",
            )

        state.set_reg(
            dst,
            value,
        )

        return

    # register <- memory / unknown expression
    state.set_reg(
        dst,
        UNKNOWN,
    )


def apply_xor(
    state: SymbolicState,
    insn: InstructionInfo,
):

    operands = split_operands(
        insn.op_str
    )

    if len(operands) != 2:
        return

    dst, src = operands

    if (
        is_register_operand(dst)
        and is_register_operand(src)
        and canonical_register(dst)
        == canonical_register(src)
    ):
        state.set_reg(
            dst,
            ZERO_VALUE,
        )
        return

    if is_register_operand(dst):
        state.set_reg(
            dst,
            UNKNOWN,
        )


def apply_lea(
    state: SymbolicState,
    insn: InstructionInfo,
):

    operands = split_operands(
        insn.op_str
    )

    if not operands:
        return

    dst = operands[0]

    if is_register_operand(dst):
        state.set_reg(
            dst,
            UNKNOWN,
        )


def apply_call(
    state: SymbolicState,
    insn: InstructionInfo,
):

    # UEFI x64 follows the Microsoft x64 ABI.
    #
    # These general-purpose registers are volatile
    # across a call. Their previous symbolic values
    # and path constraints are no longer valid.
    for register in (
        "rcx",
        "rdx",
        "r8",
        "r9",
        "r10",
        "r11",
    ):
        state.set_reg(
            register,
            UNKNOWN,
        )

    # A call also destroys our knowledge about
    # condition flags. Do not allow a later Jcc
    # to accidentally reuse flags from a cmp/test
    # performed before the call.
    state.flags_source = None

    if insn.target is not None:

        value = SymbolicValue(
            SymbolKind.FROM_CALL,
            f"0x{insn.target:X}",
            origin=insn.address,
        )

    else:

        value = SymbolicValue(
            SymbolKind.FROM_CALL,
            "indirect",
            origin=insn.address,
        )

    # set_reg() also invalidates any constraint
    # referring to the previous RAX value.
    state.set_reg(
        "rax",
        value,
    )

    state.notes.append(
        f"0x{insn.address:X}: "
        f"RAX <- {state.get_reg('rax')}"
    )


def apply_flag_instruction(
    state: SymbolicState,
    insn: InstructionInfo,
):

    state.flags_source = FlagSource(
        address=insn.address,
        mnemonic=insn.mnemonic.lower(),
        operands=insn.op_str.lower(),
    )


def normalize_conditions(
    conditions: list[str],
) -> tuple[str, ...]:

    return tuple(
        sorted(
            set(conditions)
        )
    )


def add_condition(
    state: SymbolicState,
    condition: str | None,
    source_address: int | None = None,
):

    if condition is None:
        return

    # ---------------------------------------
    # Live symbolic constraint
    #
    # Keep this address-free. It participates
    # in contradiction pruning and may later
    # be invalidated when the referenced
    # register is overwritten.
    # ---------------------------------------

    if condition not in state.conditions:
        state.conditions.append(
            condition
        )

    # ---------------------------------------
    # Historical path predicate
    #
    # Preserve provenance for diagnostics.
    # This is never invalidated when the
    # referenced register changes.
    # ---------------------------------------

    if source_address is not None:

        path_condition = (
            f"0x{source_address:X}: "
            f"{condition}"
        )

    else:

        path_condition = condition

    if (
        path_condition
        not in state.path_conditions
    ):
        state.path_conditions.append(
            path_condition
        )


def condition_from_flags(
    flags: FlagSource | None,
    condition: str,
) -> str | None:

    if flags is None:
        return None

    mnemonic = flags.mnemonic
    operands = split_operands(
        flags.operands
    )

    condition = condition.lower()

    # ---------------------------------------
    # test reg, immediate
    # ---------------------------------------

    if (
        mnemonic == "test"
        and len(operands) == 2
    ):
        reg = operands[0]
        imm = parse_immediate(
            operands[1]
        )

        if (
            is_register_operand(reg)
            and imm is not None
        ):
            reg = reg.upper()

            if condition in {
                "e",
                "z",
            }:
                return (
                    f"({reg} & 0x{imm:X}) == 0"
                )

            if condition in {
                "ne",
                "nz",
            }:
                return (
                    f"({reg} & 0x{imm:X}) != 0"
                )

    # ---------------------------------------
    # test reg, reg
    #
    # Useful for:
    #
    #   test rax, rax
    #   js ...
    #
    # ---------------------------------------

    if (
        mnemonic == "test"
        and len(operands) == 2
        and operands[0] == operands[1]
        and is_register_operand(
            operands[0]
        )
    ):
        reg = operands[0].upper()

        if condition in {
            "e",
            "z",
        }:
            return (
                f"{reg} == 0"
            )

        if condition in {
            "ne",
            "nz",
        }:
            return (
                f"{reg} != 0"
            )

        if condition == "s":
            return (
                f"{reg} < 0 (signed)"
            )

        if condition == "ns":
            return (
                f"{reg} >= 0 (signed)"
            )

    # ---------------------------------------
    # cmp reg, immediate
    # ---------------------------------------

    if (
        mnemonic == "cmp"
        and len(operands) == 2
    ):
        reg = operands[0]
        imm = parse_immediate(
            operands[1]
        )

        if (
            is_register_operand(reg)
            and imm is not None
        ):
            reg = reg.upper()

            if condition in {
                "e",
                "z",
            }:
                return (
                    f"{reg} == 0x{imm:X}"
                )

            if condition in {
                "ne",
                "nz",
            }:
                return (
                    f"{reg} != 0x{imm:X}"
                )

            if condition == "b":
                return (
                    f"{reg} < 0x{imm:X} "
                    f"(unsigned)"
                )

            if condition == "ae":
                return (
                    f"{reg} >= 0x{imm:X} "
                    f"(unsigned)"
                )

    return None

def negate_condition(
    condition: str,
) -> str | None:

    if " == " in condition:
        return condition.replace(
            " == ",
            " != ",
            1,
        )

    if " != " in condition:
        return condition.replace(
            " != ",
            " == ",
            1,
        )

    if " < " in condition:
        return condition.replace(
            " < ",
            " >= ",
            1,
        )

    if " >= " in condition:
        return condition.replace(
            " >= ",
            " < ",
            1,
        )

    if " > " in condition:
        return condition.replace(
            " > ",
            " <= ",
            1,
        )

    if " <= " in condition:
        return condition.replace(
            " <= ",
            " > ",
            1,
        )

    return None


def conditions_contradict(
    conditions: list[str],
) -> bool:

    condition_set = set(
        conditions
    )

    for condition in condition_set:

        opposite = negate_condition(
            condition
        )

        if (
            opposite is not None
            and opposite in condition_set
        ):
            return True

    return False

def apply_cmov(
    state: SymbolicState,
    insn: InstructionInfo,
) -> list[SymbolicState]:

    operands = split_operands(
        insn.op_str
    )

    if len(operands) != 2:
        return [state]

    dst, src = operands

    if not (
        is_register_operand(dst)
        and is_register_operand(src)
    ):
        return [state]

    mnemonic = insn.mnemonic.lower()

    condition_code = (
        CMOV_CONDITIONS.get(
            mnemonic
        )
    )

    # Taken condition.
    taken_condition = (
        condition_from_flags(
            state.flags_source,
            condition_code,
        )
        if condition_code
        else None
    )

    # Opposite condition.
    opposite = {
        "e": "ne",
        "z": "nz",
        "ne": "e",
        "nz": "z",
    }.get(
        condition_code
    )

    not_taken_condition = (
        condition_from_flags(
            state.flags_source,
            opposite,
        )
        if opposite
        else None
    )

    # ---------------------------------------
    # Not taken
    # ---------------------------------------

    not_taken = state.clone()

    add_condition(
        not_taken,
        not_taken_condition,
        (
            state.flags_source.address
            if state.flags_source is not None
            else None
        ),
    )

    not_taken.notes.append(
        f"0x{insn.address:X}: "
        f"{mnemonic} NOT taken; "
        f"condition="
        f"{not_taken_condition or 'unknown'}; "
        f"flags from "
        f"{state.flags_source}"
    )

    # ---------------------------------------
    # Taken
    # ---------------------------------------

    taken = state.clone()

    value = taken.get_reg(src)

    taken.set_reg(
        dst,
        value,
    )

    add_condition(
        taken,
        taken_condition,
        (
            state.flags_source.address
            if state.flags_source is not None
            else None
        ),
    )

    taken.notes.append(
        f"0x{insn.address:X}: "
        f"{mnemonic} taken: "
        f"{canonical_register(dst)} "
        f"<- {value}; "
        f"condition="
        f"{taken_condition or 'unknown'}; "
        f"flags from "
        f"{state.flags_source}"
    )

    return [
        not_taken,
        taken,
    ]


def execute_symbolic_instruction(
    state: SymbolicState,
    insn: InstructionInfo,
) -> list[SymbolicState]:

    state.path.append(
        insn.address
    )

    mnemonic = insn.mnemonic.lower()

    if mnemonic in {
        "mov",
        "movabs",
    }:
        apply_mov(
            state,
            insn,
        )
        return [state]

    if mnemonic == "xor":
        apply_xor(
            state,
            insn,
        )
        return [state]

    if mnemonic == "lea":
        apply_lea(
            state,
            insn,
        )
        return [state]

    if mnemonic == "call":
        apply_call(
            state,
            insn,
        )
        return [state]

    if mnemonic in {
        "test",
        "cmp",
        "and",
        "or",
    }:
        apply_flag_instruction(
            state,
            insn,
        )
        return [state]

    if mnemonic.startswith("cmov"):
        return apply_cmov(
            state,
            insn,
        )

    return [state]


def find_block_for_address(
    cfg: dict,
    address: int,
) -> BasicBlock | None:

    for block in cfg["blocks"].values():

        for insn in block.instructions:

            if insn.address == address:
                return block

    return None


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

                    block.edges.append(
                        CFGEdge(
                            target=insn.target,
                            kind="unconditional",
                            condition_code=None,
                        )
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

                    condition_code = JCC_CONDITIONS.get(
                        insn.mnemonic.lower()  
                    )

                    block.edges.append(
                        CFGEdge(
                            target=insn.target,
                            kind="branch_taken",
                            condition_code=condition_code,
                        )
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

                block.edges.append(
                    CFGEdge(
                        target=next_rva,
                        kind="fallthrough",
                        condition_code=(
                            OPPOSITE_CONDITION.get(
                                condition_code
                            )
                            if condition_code
                            else None
                        ),
                    )
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
                    edges=[
                        CFGEdge(
                            target=insn.address,
                            kind="fallthrough",
                            condition_code=None,
                        )
                    ],
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
                list(block.successors),
                terminal_reason=
                block.terminal_reason,
                edges=
                list(block.edges),
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

    instruction_map = reachable_instruction_map(cfg)

    addresses = sorted(
        instruction_map.keys()
    )

    results = []

    source_register = source_register.lower()

    aliases = {
        "rax": {"rax", "eax", "ax", "al", "ah"},
        "rbx": {"rbx", "ebx", "bx", "bl", "bh"},
        "rcx": {"rcx", "ecx", "cx", "cl", "ch"},
        "rdx": {"rdx", "edx", "dx", "dl", "dh"},
        "rsi": {"rsi", "esi", "si", "sil"},
        "rdi": {"rdi", "edi", "di", "dil"},
        "r12": {"r12", "r12d", "r12w", "r12b"},
        "r13": {"r13", "r13d", "r13w", "r13b"},
        "r14": {"r14", "r14d", "r14w", "r14b"},
        "r15": {"r15", "r15d", "r15w", "r15b"},
    }

    register_set = aliases.get(
        source_register,
        {source_register},
    )

    for address in addresses:

        if address <= start_address:
            continue

        if (
            address - start_address
            > max_forward_bytes
        ):
            break

        insn = instruction_map[address]

        operand_text = insn.op_str.lower()

        operands = [
            x.strip()
            for x in operand_text.split(",")
        ]

        if not operands:
            continue

        destination = operands[0]

        uses_source = any(
            reg in operand_text
            for reg in register_set
        )

        if not uses_source:
            continue

        # Record the instruction first.
        results.append({
            "address": insn.address,
            "mnemonic": insn.mnemonic,
            "operand": insn.op_str,
        })

        # If this instruction writes a NEW value into the tracked
        # register, the original definition is killed here.
        destination_is_source = (
            destination in register_set
        )

        if destination_is_source:

            # Instructions such as:
            #   mov rsi,...
            #   lea rsi,...
            #   pop rsi
            #   xor rsi,rsi
            #
            # replace the old value.
            if insn.mnemonic in {
                "mov",
                "movabs",
                "lea",
                "pop",
                "xor",
            }:
                break

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
                "already_visited": True,
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


def classify_return_check(
    check: InstructionInfo,
    branch: InstructionInfo,
) -> str:

    check_mnemonic = check.mnemonic.lower()
    check_operands = check.op_str.lower()

    branch_mnemonic = branch.mnemonic.lower()

    # Classic x64 EFI_ERROR(Status) pattern:
    #
    # test rax,rax
    # js error
    #
    if (
        check_mnemonic == "test"
        and check_operands in {
            "rax, rax",
            "eax, eax",
        }
        and branch_mnemonic in {
            "js",
            "jns",
        }
    ):
        return "probable_efi_status"

    # Comparing/testing specific bit masks generally indicates
    # a returned data/state value rather than EFI_STATUS.
    if check_mnemonic in {
        "test",
        "and",
    }:
        if (
            "0x" in check_operands
            and check_operands not in {
                "rax, rax",
                "eax, eax",
            }
        ):
            return "probable_data_or_state"

    return "unknown"


def symbolic_state_key(
    block_start: int,
    state: SymbolicState,
) -> tuple:

    registers = tuple(
        sorted(
            (
                reg,
                str(value),
                value.origin,
            )
            for reg, value
            in state.registers.items()
        )
    )

    stack_slots = tuple(
        sorted(
            (
                slot,
                str(value),
                value.origin,
            )
            for slot, value
            in state.stack_slots.items()
        )
    )

    conditions = normalize_conditions(
        state.conditions
    )

    return (
        block_start,
        registers,
        stack_slots,
        str(state.flags_source),
        conditions,
    )

def run_symbolic_cfg(
    cfg: dict,
    max_states: int = 1000,
    max_steps_per_state: int = 1000,
) -> list[SymbolicState]:

    blocks = cfg["blocks"]

    start = cfg["start_rva"]

    initial = SymbolicState()

    pending = [
        (
            start,
            initial,
        )
    ]

    completed = []
    truncated = []
    processed_states = 0
    seen_states = set()

    while pending:

        block_start, state = (
            pending.pop()
        )

        state_key = symbolic_state_key(
            block_start,
            state,
        )

        if state_key in seen_states:
            continue

        seen_states.add(
            state_key
        )

        state.block_visits[
            block_start
        ] = (
            state.block_visits.get(
                block_start,
                0,
            )
            + 1
        )

        if state.block_visits[block_start] > 12:
            state.notes.append(
                f"Loop visit limit reached "
                f"at 0x{block_start:X}"
            )
            truncated.append(state)
            continue

        processed_states += 1

        if processed_states > max_states:
            state.notes.append(
                "GLOBAL STATE LIMIT REACHED"
            )
            truncated.append(state)
            break

        block = blocks.get(
            block_start
        )

        if block is None:
            state.notes.append(
                f"Missing block 0x{block_start:X}"
            )
            completed.append(state)
            continue

        states = [state]

        step_count = 0

        for insn in block.instructions:

            step_count += 1

            if (
                step_count
                > max_steps_per_state
            ):
                for s in states:
                    s.notes.append(
                        "BLOCK STEP LIMIT REACHED"
                    )

                break

            new_states = []

            for current_state in states:

                generated = (
                    execute_symbolic_instruction(
                        current_state,
                        insn,
                    )
                )

                for candidate in generated:

                    candidate.conditions = list(
                        normalize_conditions(
                            candidate.conditions
                        )
                    )

                    if conditions_contradict(
                        candidate.conditions
                    ):
                        continue

                    new_states.append(
                        candidate
                    )

            states = new_states

        # No outgoing CFG edge means this path
        # terminates here.
        #
        # Prefer explicit edge metadata, but keep
        # successors as a compatibility fallback.
        has_edges = bool(
            getattr(
                block,
                "edges",
                None,
            )
        )

        if (
            not has_edges
            and not block.successors
        ):

            completed.extend(
                states
            )

            continue

        # Prefer condition-aware CFGEdge metadata.
        #
        # Older/legacy blocks may still only have
        # successors, so synthesize neutral edges
        # in that case.
        if has_edges:

            edges = block.edges

        else:

            edges = [
                CFGEdge(
                    target=successor,
                    kind="legacy",
                    condition_code=None,
                )
                for successor
                in block.successors
            ]

        for current_state in states:

            for edge in edges:

                child = (
                    current_state.clone()
                )

                # Apply branch predicate derived
                # from the current flags producer.
                if (
                    edge.condition_code
                    is not None
                ):

                    condition = (
                        condition_from_flags(
                            child.flags_source,
                            edge.condition_code,
                        )
                    )

                    if condition is not None:

                        add_condition(
                            child,
                            condition,
                            (
                                child.flags_source.address
                                if child.flags_source is not None
                                else None
                            ),
                        )
                        
                        child.conditions = list(
                            normalize_conditions(
                                child.conditions
                            )
                        )

                        if conditions_contradict(
                            child.conditions
                        ):
                            continue

                    else:

                        child.notes.append(
                            f"CFG edge condition "
                            f"unknown: "
                            f"{edge.condition_code}"
                        )

                child.notes.append(
                    f"CFG edge "
                    f"0x{block.start:X} "
                    f"-> 0x{edge.target:X}; "
                    f"kind={edge.kind}; "
                    f"condition="
                    f"{edge.condition_code or 'none'}"
                )

                pending.append(
                    (
                        edge.target,
                        child,
                    )
                )

    return completed


def summarize_return_states(
    states: list[SymbolicState],
) -> list[dict]:

    grouped = {}

    for state in states:

        rax = state.get_reg(
            "rax"
        )

        if (
            rax.kind
            == SymbolKind.UNKNOWN
        ):
            continue

        condition_key = normalize_conditions(
            state.conditions
        )

        path_condition_key = normalize_conditions(
            state.path_conditions
        )

        key = (
            str(rax),
            rax.origin,
            condition_key,
        )

        if key not in grouped:
            grouped[key] = {
                "rax": str(rax),

                "origin": (
                    f"0x{rax.origin:X}"
                    if rax.origin is not None
                    else None
                ),

                "count": 0,

                "conditions": list(
                    condition_key
                ),

                "path_condition_sets": [
                    list(
                        path_condition_key
                    )
                ],

                "example_path_tail": [
                    f"0x{x:X}"
                    for x
                    in state.path[-20:]
                ],

                "example_notes_tail":
                    state.notes[-20:],
            }

        path_conditions = list(
            path_condition_key
        )

        if (
            path_conditions
            not in grouped[key][
                "path_condition_sets"
            ]
        ):
            grouped[key][
                "path_condition_sets"
            ].append(
                path_conditions
            )

        grouped[key]["count"] += 1

    return list(
        grouped.values()
    )

@function_tool
def analyze_symbolic_returns(
    relative_path: str,
    start_rva: int,
    max_bytes: int = 4096,
    max_states: int = 500,
) -> str:
    """
    Perform lightweight path-sensitive symbolic analysis
    and summarize possible RAX return values.
    """

    cfg = build_cfg_internal(
        relative_path,
        start_rva,
        max_bytes,
    )

    states = run_symbolic_cfg(
        cfg,
        max_states=max_states,
    )

    summaries = summarize_return_states(
        states
    )

    import json

    return json.dumps(
        {
            "function": (
                f"0x{start_rva:X}"
            ),
            "completed_states": (
                len(states)
            ),
            "return_states": summaries,
        },
        indent=2,
    )


def summarize_efi_error_returns(
    states: list[SymbolicState],
) -> list[dict]:

    matching = []

    for state in states:

        rax = state.get_reg(
            "rax"
        )

        if (
            rax.kind
            != SymbolKind.EFI_DEVICE_ERROR
        ):
            continue

        matching.append(state)

    if not matching:
        return []

    examples = []

    seen_tails = set()

    for state in matching:

        tail = tuple(
            state.path[-20:]
        )

        if tail in seen_tails:
            continue

        seen_tails.add(tail)

        examples.append({
            "path_tail": [
                f"0x{x:X}"
                for x in tail
            ],

            "notes_tail":
                state.notes[-20:],
        })

        if len(examples) >= 5:
            break

    return [{
        "return": "EFI_DEVICE_ERROR",
        "state_count": len(matching),
        "example_paths": examples,
    }]


def summarize_call_derived_returns(
    states: list[SymbolicState],
) -> list[dict]:

    grouped = {}

    for state in states:

        rax = state.get_reg(
            "rax"
        )

        if (
            rax.kind
            != SymbolKind.FROM_CALL
        ):
            continue

        condition_key = normalize_conditions(
            state.conditions
        )

        key = (
            str(rax),
            rax.origin,
            condition_key,
        )

        if key not in grouped:
            grouped[key] = {
                "return": str(rax),
                "origin": (
                    f"0x{rax.origin:X}"
                    if rax.origin is not None
                    else None
                ),
                "count": 0,
                "example_path_tail": [
                    f"0x{x:X}"
                    for x
                    in state.path[-30:]
                ],
                "example_notes_tail":
                    state.notes[-30:],
                "conditions": list(
                  condition_key
                ),
            }

        grouped[key]["count"] += 1

    return list(
        grouped.values()
    )


STACK_SLOT_RE = re.compile(
    r"^(?:qword ptr |dword ptr |word ptr |byte ptr )?"
    r"\[rsp(?: \+ (0x[0-9a-f]+|\d+))?\]$"
)


def normalize_stack_slot(
    operand: str,
) -> str | None:

    operand = operand.lower().strip()

    match = STACK_SLOT_RE.match(
        operand
    )

    if not match:
        return None

    offset_text = match.group(1)

    if offset_text is None:
        offset = 0
    else:
        offset = int(
            offset_text,
            0,
        )

    return f"rsp+0x{offset:X}"


def summarize_unknown_returns(
    states: list[SymbolicState],
    max_examples: int = 5,
) -> dict:

    matching = []

    for state in states:

        rax = state.get_reg(
            "rax"
        )

        if (
            rax.kind
            != SymbolKind.UNKNOWN
        ):
            continue

        matching.append(state)

    examples = []

    for state in matching[:max_examples]:

        examples.append({
            "conditions": list(
                state.conditions
            ),

            "path_tail": [
                f"0x{x:X}"
                for x
                in state.path[-20:]
            ],

            "notes_tail":
                state.notes[-20:],
        })

    return {
        "count": len(matching),
        "examples": examples,
    }