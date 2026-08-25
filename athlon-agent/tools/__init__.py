from .filesystem import (
    list_files,
    read_text_file,
)

from .binaries import (
    file_info,
    read_binary_range,
    find_hex_pattern,
)

from .scripts import (
    run_project_script,
)

from .disassembly import (
    inspect_pe,
    rva_to_file_offset,
    disassemble_function,
    analyze_control_transfers,
    find_efi_device_error_immediates,
    find_call_status_checks,
)

ALL_TOOLS = [
    list_files,
    read_text_file,

    file_info,
    read_binary_range,
    find_hex_pattern,

    inspect_pe,
    rva_to_file_offset,
    disassemble_function,
    analyze_control_transfers,
    find_efi_device_error_immediates,
    find_call_status_checks,

    run_project_script,
]