#!/usr/bin/env python3
"""
ORBIT - Open-Source Reference Benchmark for IoT Cryptography
Benchmark Manager Script.

Usage:
    python3 tools/orbit.py --board pico --algo ascon_aead128 --runs 5
    python3 tools/orbit.py --board pico --algo ascon_aead128 --runs 5 --output results/run1.csv
    python3 tools/orbit.py --board pico --algo ascon_aead128 --runs 5 --flash
"""

import argparse
import csv
import io
import os
import subprocess
import sys
import time
import re
import shutil
import glob
import shlex
from datetime import datetime, timezone

import serial
import serial.tools.list_ports

# ----- Board Definitions -----

BOARDS = {
    "pico": {
        "name": "Raspberry Pi Pico (RP2040)",
        "arch": "armv6-m",
        "flash_method": "uf2",
        "baud": 115200,
    },
    "nrf52": {
        "name": "Nordic nRF52840 DK (PCA10056)",
        "arch": "armv7e-m",
        "flash_method": "nrfjprog",
        "baud": 115200,
    },
    "stm32": {
        "name": "STM32 Nucleo F446RE",
        "arch": "armv7e-m",
        "flash_method": "openocd",
        "baud": 115200,
    },
    "esp32c61": {
        "name": "ESP32-C61",
        "arch": "riscv32",
        "flash_method": "idf.py",
        "baud": 115200,
    },
    "rpi5": {
        "name": "Raspberry Pi 5",
        "arch": "aarch64",
        "flash_method": "local",
        "baud": None,
    },
}

# ----- Algorithm Definitions -----
ALGORITHMS = [
    "ascon_aead128",
    "ascon_aead80pq",
    "gift_cofb",
    "aes_128_gcm",
    "ml_kem_512",
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
ARCHIVE_DIR = os.path.join(RESULTS_DIR, "archived")
IDF_BOARDS = {
    "esp32c61": {
        "idf_target": "esp32c61",
        "project_dir": os.path.join(PROJECT_ROOT, "platforms", "esp32c61"),
    },
}

TIMESTAMP_COL = "timestamp_iso"
RUN_ID_COL = "run_id"
DEFAULT_CSV_HEADER = (
    "timestamp_iso,run_id,algorithm,implementation,version,board,arch,"
    "compiler,compiler_version,cflags,freq_hz,msg_len,ad_len,key_len,"
    "nonce_len,tag_len,iterations,enc_cycles_total,dec_cycles_total,"
    "enc_cycles_per_byte,dec_cycles_per_byte,enc_time_us_total,"
    "dec_time_us_total,enc_time_us_per_op,dec_time_us_per_op,flash_bytes,"
    "ram_bytes,stack_bytes_peak,energy_uJ_enc_total,energy_uJ_dec_total,"
    "energy_uJ_per_byte_enc,energy_uJ_per_byte_dec,avg_power_mW_enc,"
    "avg_power_mW_dec,ok,notes"
)


def is_wsl():
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False

FLASH_FUNCS = {
    "pico": lambda binary: flash_pico(binary),
    "stm32": lambda binary: flash_stm32(binary),
    "nrf52": lambda binary: flash_nrf52(binary),
    # "rpi5":    lambda binary: flash_rpi5(binary),
}

# ----- Logging -----
def log(msg):
    print(f"[ORBIT] {msg}")

def archive_existing_result(path: str) -> None:
    if not os.path.exists(path):
        return

    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    base_name = os.path.basename(path)
    stem, ext = os.path.splitext(base_name)
    candidate = os.path.join(ARCHIVE_DIR, base_name)
    index = 1

    while os.path.exists(candidate):
        candidate = os.path.join(ARCHIVE_DIR, f"{stem}_{index}{ext}")
        index += 1

    shutil.move(path, candidate)
    log(f"Archived existing output to: {candidate}")

# ----- Timestamp Formatting -----
def host_timestamp_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _compact_ts(iso: str) -> str:
    return re.sub(r"[-:]", "", iso).replace("Z", "Z")

def make_run_id(ts_iso: str, algorithm: str, board: str, arch: str) -> str:
    compact = _compact_ts(ts_iso)
    def slug(s):
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return f"{compact}_{slug(algorithm)}_{slug(board)}_{slug(arch)}"

def postprocess_csv(input_path: str, output_path: str | None = None) -> None:
    if output_path is None:
        output_path = input_path

    mtime = os.path.getmtime(input_path)
    file_ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    log(f"Post-processing CSV: {input_path}")
    log(f"File timestamp (UTC): {file_ts}")

    expected_fieldnames = ["run"] + next(csv.reader([DEFAULT_CSV_HEADER]))

    with open(input_path, newline="", encoding="utf-8") as infile:
        raw_rows = list(csv.reader(infile))
        if not raw_rows:
            log("Error: CSV file has no header")
            sys.exit(1)

    header = raw_rows[0]
    if header != expected_fieldnames:
        log("Warning: CSV header did not match expected ORBIT schema; repairing header and trimming malformed fields.")

    rows = []
    for raw in raw_rows[1:]:
        if len(raw) < len(expected_fieldnames):
            log(f"Warning: skipping short CSV row with {len(raw)} field(s): {raw[:4]}")
            continue
        if len(raw) > len(expected_fieldnames):
            log(f"Warning: trimming malformed CSV row from {len(raw)} to {len(expected_fieldnames)} fields")
            raw = raw[:len(expected_fieldnames)]
        rows.append(dict(zip(expected_fieldnames, raw)))
    
    epoch_pattern = re.compile(r"^1970-")
    fixed = 0

    for row in rows:
        if epoch_pattern.match(row.get(TIMESTAMP_COL, "")):
            row[TIMESTAMP_COL] = file_ts
            row[RUN_ID_COL] = make_run_id(file_ts, row.get("algorithm", "unknown"), row.get("board", "unknown"), row.get("arch", "unknown"))
            fixed += 1
    
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=expected_fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    with open(output_path, "w", newline="", encoding="utf-8") as outfile:
        outfile.write(buf.getvalue())

    log(f"Fixed {fixed} timestamp(s) in CSV. Written to: {output_path}")

# ----- Build and Flashing -----

def run_command(cmd, cwd=None):
    print(f"Running: {cmd}")
    ret = subprocess.call(cmd, shell=True, cwd=cwd)
    if ret != 0:
        print(f"Command failed with exit code {ret}")
        sys.exit(1)


def run_capture(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def command_exists(name):
    return shutil.which(name) is not None


def check_version_command(cmd):
    try:
        result = run_capture(cmd)
    except OSError as exc:
        return False, str(exc)

    output = (result.stdout or result.stderr).strip().splitlines()
    message = output[0] if output else "command returned no version text"
    return result.returncode == 0, message


def resolve_stm32cube_path():
    return (
        os.environ.get("STM32CUBE_F4_PATH")
        or os.path.join(os.path.expanduser("~"), "stm32cubeF4")
    )


def resolve_pico_sdk_path():
    return os.environ.get("PICO_SDK_PATH")


def resolve_nrf5_sdk_path():
    return os.environ.get("NRF5_SDK_PATH") or os.path.join(
        os.path.expanduser("~"), "nRF5_SDK"
    )


def check_item(label, ok, detail, failures, required=True):
    status = "OK" if ok else "MISSING"
    print(f"[{status:<7}] {label}: {detail}")
    if required and not ok:
        failures.append(label)


def run_prereq_check(board=None):
    failures = []

    print("== ORBIT host check ==")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Environment: {'WSL2' if is_wsl() else 'native Linux/other'}")

    python_ok = sys.version_info >= (3, 12)
    check_item(
        "Python",
        python_ok,
        sys.version.split()[0],
        failures,
    )

    for label, command in (
        ("cmake", ["cmake", "--version"]),
        ("arm-none-eabi-gcc", ["arm-none-eabi-gcc", "--version"]),
    ):
        if command_exists(command[0]):
            ok, detail = check_version_command(command)
            check_item(label, ok, detail, failures)
        else:
            check_item(label, False, "not found on PATH", failures)

    if os.path.isdir(os.path.join(PROJECT_ROOT, ".venv")):
        check_item(".venv", True, "present", failures)
    else:
        check_item(".venv", False, "missing; run ./setup.sh", failures)

    ports = [port.device for port in serial.tools.list_ports.comports()]
    port_detail = ", ".join(ports) if ports else "no ttyACM/ttyUSB devices visible right now"
    check_item("Serial devices", True, port_detail, failures, required=False)

    boards_to_check = [board] if board else ["pico", "stm32", "nrf52", "esp32c61", "rpi5"]

    if "pico" in boards_to_check:
        print("\n== Pico ==")
        pico_sdk_path = resolve_pico_sdk_path()
        pico_sdk_ok = bool(
            pico_sdk_path
            and os.path.exists(
                os.path.join(pico_sdk_path, "external", "pico_sdk_import.cmake")
            )
        )
        check_item(
            "PICO_SDK_PATH",
            pico_sdk_ok,
            pico_sdk_path or "unset",
            failures,
        )

        if command_exists("picotool"):
            ok, detail = check_version_command(["picotool", "version"])
            check_item("picotool", ok, detail, failures)
        else:
            check_item("picotool", False, "not found on PATH", failures)

        mount_ok = os.path.isdir("/mnt/pico")
        check_item(
            "/mnt/pico",
            mount_ok,
            "present" if mount_ok else "missing; run ./setup.sh",
            failures,
        )

        attach_script = os.path.join(PROJECT_ROOT, "scripts", "attach_pico.ps1")
        check_item(
            "attach_pico.ps1",
            os.path.exists(attach_script),
            attach_script,
            failures,
        )

        if is_wsl():
            check_item(
                "powershell.exe",
                command_exists("powershell.exe"),
                shutil.which("powershell.exe") or "not found on PATH",
                failures,
            )

    if "stm32" in boards_to_check:
        print("\n== STM32 ==")
        stm32cube_path = resolve_stm32cube_path()
        stm32cube_ok = os.path.exists(
            os.path.join(
                stm32cube_path,
                "Drivers",
                "CMSIS",
                "Device",
                "ST",
                "STM32F4xx",
                "Include",
                "stm32f4xx.h",
            )
        )
        check_item(
            "STM32CUBE_F4_PATH",
            stm32cube_ok,
            stm32cube_path,
            failures,
        )

        if command_exists("openocd"):
            ok, detail = check_version_command(["openocd", "--version"])
            check_item("openocd", ok, detail, failures)
        else:
            check_item("openocd", False, "not found on PATH", failures)

        openocd_cfg = os.environ.get(
            "ORBIT_STM32_OPENOCD_CFG",
            "interface/stlink.cfg -f target/stm32f4x.cfg",
        )
        check_item("OpenOCD config", True, openocd_cfg, failures, required=False)

    if "nrf52" in boards_to_check:
        print("\n== nRF52 ==")
        nrf5_sdk_path = resolve_nrf5_sdk_path()
        nrf5_sdk_ok = os.path.exists(
            os.path.join(nrf5_sdk_path, "modules", "nrfx", "mdk", "nrf.h")
        )
        check_item(
            "NRF5_SDK_PATH",
            nrf5_sdk_ok,
            nrf5_sdk_path,
            failures,
        )

        if command_exists("nrfjprog"):
            ok, detail = check_version_command(["nrfjprog", "--version"])
            check_item("nrfjprog", ok, detail, failures)
        else:
            check_item("nrfjprog", False, "not found on PATH", failures)

    if "esp32c61" in boards_to_check:
        print("\n== ESP32-C61 ==")
        idf_path = os.environ.get("IDF_PATH")
        idf_project = IDF_BOARDS["esp32c61"]["project_dir"]
        check_item(
            "IDF_PATH",
            bool(idf_path and os.path.isdir(idf_path)),
            idf_path or "unset; run . ~/esp/esp-idf/export.sh",
            failures,
        )

        if command_exists("idf.py"):
            ok, detail = check_version_command(["idf.py", "--version"])
            check_item("idf.py", ok, detail, failures)
        else:
            check_item("idf.py", False, "not found on PATH; run . ~/esp/esp-idf/export.sh", failures)

        if command_exists("esptool.py"):
            ok, detail = check_version_command(["esptool.py", "version"])
            check_item("esptool.py", ok, detail, failures)
        else:
            check_item("esptool.py", False, "not found on PATH after ESP-IDF export", failures)

        check_item(
            "ESP-IDF project",
            os.path.exists(os.path.join(idf_project, "CMakeLists.txt")),
            idf_project,
            failures,
        )

    if "rpi5" in boards_to_check:
        print("\n== RPi5 ==")
        for label, command in (
            ("cc", ["cc", "--version"]),
        ):
            if command_exists(command[0]):
                ok, detail = check_version_command(command)
                check_item(label, ok, detail, failures)
            else:
                check_item(label, False, "not found on PATH", failures)

    if failures:
        print("\nMissing prerequisites:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nAll required prerequisites are present.")
    return 0

def find_build_artifact(board, algo):
    target_name = f"ORBIT_{algo}_{board}"
    candidates = []

    if board in IDF_BOARDS:
        idf_build_dir = idf_build_dir_for(board, algo)
        candidates.extend([
            os.path.join(idf_build_dir, f"{target_name}.bin"),
            os.path.join(idf_build_dir, f"{target_name}.elf"),
        ])
    elif board == "pico":
        candidates.extend([
            os.path.join(BUILD_DIR, f"{target_name}.uf2"),
            os.path.join(BUILD_DIR, target_name),
        ])
    elif board == "stm32":
        candidates.extend([
            os.path.join(BUILD_DIR, f"{target_name}.bin"),
            os.path.join(BUILD_DIR, target_name),
        ])
    elif board == "nrf52":
        candidates.extend([
            os.path.join(BUILD_DIR, f"{target_name}.hex"),
            os.path.join(BUILD_DIR, f"{target_name}.bin"),
            os.path.join(BUILD_DIR, target_name),
        ])
    elif board == "rpi5":
        candidates.extend([
            os.path.join(BUILD_DIR, target_name),
            os.path.join(BUILD_DIR, f"{target_name}.elf"),
        ])
    else:
        candidates.extend([
            os.path.join(BUILD_DIR, f"{target_name}.elf"),
            os.path.join(BUILD_DIR, target_name),
        ])

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def idf_build_dir_for(board, algo):
    return os.path.join(BUILD_DIR, f"{board}_{algo}")


def resolve_size_input(board, algo, artifact):
    target_name = f"ORBIT_{algo}_{board}"
    if board in IDF_BOARDS:
        idf_build_dir = idf_build_dir_for(board, algo)
        candidates = [
            os.path.join(idf_build_dir, f"{target_name}.elf"),
            artifact,
        ]
    else:
        candidates = [
            os.path.join(BUILD_DIR, f"{target_name}.elf"),
            os.path.join(BUILD_DIR, target_name),
            artifact,
        ]

    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def extract_memory_metrics(board, algo, artifact):
    metrics = {"flash_bytes": 0, "ram_bytes": 0, "stack_bytes_peak": 0}
    size_input = resolve_size_input(board, algo, artifact)
    if size_input is None:
        return metrics

    if board in {"pico", "stm32", "nrf52"}:
        size_tool = "arm-none-eabi-size"
    elif board in IDF_BOARDS:
        size_tool = "riscv32-esp-elf-size"
    else:
        size_tool = "size"
    if not command_exists(size_tool):
        return metrics

    result = run_capture([size_tool, size_input])
    if result.returncode != 0:
        return metrics

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return metrics

    parts = lines[1].split()
    if len(parts) < 4:
        return metrics

    try:
        text = int(parts[0])
        data = int(parts[1])
        bss = int(parts[2])
    except ValueError:
        return metrics

    metrics["flash_bytes"] = text + data
    metrics["ram_bytes"] = data + bss
    return metrics


def _cache_value(cache_path, key):
    if not os.path.exists(cache_path):
        return None

    prefix = f"{key}:"
    with open(cache_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith(prefix):
                _, value = line.split("=", 1)
                return value.strip()
    return None


def should_clean_for_board_switch(board):
    cache_path = os.path.join(BUILD_DIR, "CMakeCache.txt")
    if not os.path.exists(cache_path):
        return False

    cached_board = _cache_value(cache_path, "BOARD")
    cached_c_compiler = _cache_value(cache_path, "CMAKE_C_COMPILER") or ""
    cached_pico_board = _cache_value(cache_path, "PICO_BOARD")

    if cached_board and cached_board != board:
        return True

    if board == "rpi5" and "arm-none-eabi" in cached_c_compiler:
        return True

    if board in {"pico", "stm32", "nrf52"} and cached_board == "rpi5":
        return True

    if board != "pico" and cached_pico_board:
        return True

    return False

def build(board, algo, clean=False, energy_runs=None, no_stdio_wait=False):
    if board in IDF_BOARDS:
        return build_idf(board, algo, clean=clean, energy_runs=energy_runs, no_stdio_wait=no_stdio_wait)

    if not clean and should_clean_for_board_switch(board):
        log("Detected incompatible cached build configuration; cleaning build directory first...")
        clean = True

    if clean and os.path.exists(BUILD_DIR):
        log(f"Cleaning build directory '{BUILD_DIR}'...")
        shutil.rmtree(BUILD_DIR)

    os.makedirs(BUILD_DIR, exist_ok=True)

    log(f"Configuring for {board} with algorithm {algo}...")
    extra_cmake_args = ""
    if board in {"stm32", "nrf52"}:
        extra_cmake_args = (
            " -DCMAKE_C_COMPILER=arm-none-eabi-gcc"
            " -DCMAKE_CXX_COMPILER=arm-none-eabi-g++"
            " -DCMAKE_ASM_COMPILER=arm-none-eabi-gcc"
            " -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY"
        )
    if energy_runs is not None:
        extra_cmake_args += f" -DORBIT_ENERGY_RUNS={int(energy_runs)}"
    if no_stdio_wait:
        extra_cmake_args += " -DORBIT_NO_STDIO_WAIT=ON"
    run_command(
        f"cmake -S {PROJECT_ROOT} -B {BUILD_DIR} "
        f"-DBOARD={board} "
        f"-DALGO_SELECTED={algo}"
        f"{extra_cmake_args}",
    )

    log("Building...")
    run_command(f"cmake --build {BUILD_DIR} --config Release -- -j4")

    artifact = find_build_artifact(board, algo)
    if artifact is None:
        log("Build failed: No output file found.")
        sys.exit(1)
    log(f"Build successful. Artifact located at: {artifact}")
    return artifact


def build_idf(board, algo, clean=False, energy_runs=None, no_stdio_wait=False):
    if not command_exists("idf.py"):
        log("ESP-IDF is not active: idf.py was not found on PATH.")
        log("Run: . ~/esp/esp-idf/export.sh")
        sys.exit(1)

    board_cfg = IDF_BOARDS[board]
    project_dir = board_cfg["project_dir"]
    idf_build_dir = idf_build_dir_for(board, algo)
    target = board_cfg["idf_target"]

    if clean and os.path.exists(idf_build_dir):
        log(f"Cleaning ESP-IDF build directory '{idf_build_dir}'...")
        shutil.rmtree(idf_build_dir)

    os.makedirs(BUILD_DIR, exist_ok=True)

    q_project = shlex.quote(project_dir)
    q_build = shlex.quote(idf_build_dir)
    q_root = shlex.quote(PROJECT_ROOT)
    q_algo = shlex.quote(algo)
    energy_args = ""
    if energy_runs is not None:
        energy_args += f" -DORBIT_ENERGY_RUNS={int(energy_runs)}"
    if no_stdio_wait:
        energy_args += " -DORBIT_NO_STDIO_WAIT=ON"

    log(f"Configuring ESP-IDF target {target} with algorithm {algo}...")
    run_command(
        f"idf.py -C {q_project} -B {q_build} "
        f"-DALGO_SELECTED={q_algo} -DORBIT_ROOT={q_root} "
        f"{energy_args} "
        f"set-target {target}"
    )

    log("Building with ESP-IDF...")
    run_command(
        f"idf.py -C {q_project} -B {q_build} "
        f"-DALGO_SELECTED={q_algo} -DORBIT_ROOT={q_root} "
        f"{energy_args} "
        "build"
    )

    artifact = find_build_artifact(board, algo)
    if artifact is None:
        log("ESP-IDF build failed: No output file found.")
        sys.exit(1)
    log(f"Build successful. Artifact located at: {artifact}")
    return artifact

def _attach_pico_wsl():
    """
    Call the powershell attach script from WSL2 to reattach the Pico
    after a BOOTSEL replug. powershell.exe is accessible from WSL2.
    """
    ps_script = os.path.join(PROJECT_ROOT, "scripts", "attach_pico.ps1")
        
    if not os.path.exists(ps_script):
        log("attach_pico.ps1 not found, trying inline usbipd command...")
        cmd = (
            'powershell.exe -Command "'
            '$d = usbipd list | Select-String \\"2e8a:0003\\"; '
            'if ($d) { $b = ($d[0].Line -split \\"\\\\s+\\")[0].Trim(); '
            'usbipd attach --wsl --busid $b; '
            'Write-Host \\"Attached $b\\" }"'
        )
        ret = subprocess.call(cmd, shell=True)
        return ret == 0

    # Copy script to Windows temp directory (accessible to powershell.exe)
    win_temp = "/mnt/c/Windows/Temp/attach_pico.ps1"
    try:
        shutil.copy(ps_script, win_temp)
    except Exception as e:
        log(f"Could not copy script to Windows temp: {e}")
        return False

    log("Running attach_pico.ps1 via powershell.exe...")
    ret = subprocess.call(
        'powershell.exe -ExecutionPolicy RemoteSigned -File "C:\\Windows\\Temp\\attach_pico.ps1"',
        shell=True
    )
    return ret == 0

def flash_pico(binary_path):
    uid = os.getuid()
    gid = os.getgid()
    mount_point = None

    log("Attempting picotool reboot into BOOTSEL mode...")
    ret = subprocess.call(
        "picotool reboot -f -u",
        shell=True,
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL
    )

    if ret == 0:
        log("Picotool reboot successful.")
        time.sleep(3)
    else:
        log("Picotool reboot failed: Pico may already be in BOOTSEL or unpowered.")

    log("Reattaching Pico to WSL2 via usbipd...")
    _attach_pico_wsl()
    time.sleep(2)

    # Check if already mounted from a manual mount
    if os.path.exists("/mnt/pico/INFO_UF2.TXT"):
        mount_point = "/mnt/pico"
        log("Found Pico at /mnt/pico (already mounted)")
    else:
        # Try to find and mount automatically
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,SIZE,RM,TYPE", "--noheadings"],
                capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[3] == "part" and parts[2] == "1" and "128M" in parts[1]:
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '', parts[0])
                    device = f"/dev/{clean_name}"
                    os.makedirs("/mnt/pico", exist_ok=True)
                    mount_cmd = f"sudo mount -o rw,uid={uid},gid={gid} {device} /mnt/pico"
                    log(f"Attempting: {mount_cmd}")
                    ret = subprocess.call(mount_cmd, shell=True)
                    log(f"Mount return code: {ret}")
                    time.sleep(1)
                    if os.path.exists("/mnt/pico/INFO_UF2.TXT"):
                        mount_point = "/mnt/pico"
                        log(f"Auto-mounted {device} at /mnt/pico")
                    else:
                        log(f"Mount succeeded (rc={ret}) but INFO_UF2.TXT not found")
                        log(f"Contents of /mnt/pico: {os.listdir('/mnt/pico') if os.path.exists('/mnt/pico') else 'directory missing'}")
                    break
        except Exception as e:
            log(f"Auto-mount scan failed: {e}")

    # Fall back to asking user
    if not mount_point:
        log("Auto-mount failed. Please mount manually in another terminal:")
        log("  lsblk  then  sudo mount -o rw,uid=$(id -u),gid=$(id -g) /dev/sdX1 /mnt/pico")
        input("Press Enter once /mnt/pico shows INFO_UF2.TXT ...")
        mount_point = "/mnt/pico"

    log(f"Copying {os.path.basename(binary_path)} -> {mount_point} ...")
    shutil.copy(binary_path, mount_point)
    log("Flash complete. Pico rebooting...")

    subprocess.call("sudo umount /mnt/pico", shell=True, stderr=subprocess.DEVNULL)
    log("Unmounted /mnt/pico.")

    log("Waiting for Pico to reboot into firmware mode...")
    time.sleep(8)

    log("Reattaching Pico serial device to WSL2...")
    _attach_pico_wsl()
    time.sleep(3)

def flash_pico_for_run(binary_path, run):
    if run == 1:
        log("Run 1 requires Pico in BOOTSEL mode before flashing:")
        log("  1. Hold BOOTSEL button")
        log("  2. Unplug USB")
        log("  3. Plug USB back in")
        log("  4. Release BOOTSEL")
        input("Press Enter once Pico is in BOOTSEL mode ...")
    else:
        log(f"Run {run}: picotool will reboot Pico into BOOTSEL automatically...")

    flash_pico(binary_path)

def flash_stm32(binary_path):
    openocd_cfg = os.environ.get(
        "ORBIT_STM32_OPENOCD_CFG",
        "interface/stlink.cfg -f target/stm32f4x.cfg"
    )

    if binary_path.endswith(".bin"):
        flash_cmd = (
            f'openocd -f {openocd_cfg} '
            f'-c "init; reset init; program {binary_path} 0x08000000 verify; reset halt; shutdown"'
        )
    else:
        flash_cmd = (
            f'openocd -f {openocd_cfg} '
            f'-c "init; reset init; program {binary_path} verify; reset halt; shutdown"'
        )

    log("Flashing STM32 via OpenOCD...")
    run_command(flash_cmd)
    time.sleep(2)


def stm32_reset_cmd():
    openocd_cfg = os.environ.get(
        "ORBIT_STM32_OPENOCD_CFG",
        "interface/stlink.cfg -f target/stm32f4x.cfg"
    )
    return f'openocd -f {openocd_cfg} -c "init; reset run; shutdown"'


def flash_nrf52(binary_path):
    if binary_path.endswith(".hex"):
        flash_cmd = f'nrfjprog --eraseall -f nrf52 && nrfjprog --program "{binary_path}" --verify -f nrf52'
    else:
        flash_cmd = f'nrfjprog --eraseall -f nrf52 && nrfjprog --program "{binary_path}" --sectorerase --verify -f nrf52'

    log("Flashing nRF52 via nrfjprog...")
    run_command(flash_cmd)
    time.sleep(1)


def flash_idf(board, algo, port=None):
    board_cfg = IDF_BOARDS[board]
    project_dir = board_cfg["project_dir"]
    idf_build_dir = idf_build_dir_for(board, algo)

    cmd = (
        f"idf.py -C {shlex.quote(project_dir)} -B {shlex.quote(idf_build_dir)} "
        f"-DALGO_SELECTED={shlex.quote(algo)} -DORBIT_ROOT={shlex.quote(PROJECT_ROOT)} "
    )
    if port:
        cmd += f"-p {shlex.quote(port)} "
    cmd += "flash"

    log(f"Flashing {BOARDS[board]['name']} via ESP-IDF...")
    run_command(cmd)
    time.sleep(2)
# ----- Serial Capture and Result Processing -----

def _serial_port_sort_key(device: str):
    match = re.search(r"tty(?:ACM|USB)(\d+)$", device)
    if match:
        return (0, int(match.group(1)))
    return (1, device)


def find_serial_port(baud=115200, timeout=30):
    log(f"Waiting for serial port (timeout {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        ports = sorted(
            serial.tools.list_ports.comports(),
            key=lambda p: _serial_port_sort_key(p.device),
        )
        for port in ports:
            if "ttyACM" in port.device or "ttyUSB" in port.device:
                log(f"Found serial port: {port.device}")
                return port.device
        time.sleep(0.5)
    log("No serial port found within timeout.")
    return None

def capture_serial(port, baud=115200, timeout=300):
    log(f"Opening {port} at {baud} baud...")
    lines = []
    pending = ""

    try:
        with serial.Serial(port, baudrate=baud, timeout=1) as ser:
            start = time.time()
            while time.time() - start < timeout:
                chunk = ser.read(ser.in_waiting or 1)
                if not chunk:
                    continue

                text = chunk.decode("utf-8", errors="replace")
                pending += text

                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line:
                        continue
                    print(f"    {line}")
                    lines.append(line)
                    if "ORBIT benchmark completed" in line:
                        log("Benchmark complete signal received")
                        return lines

            if pending.strip():
                line = pending.rstrip("\r")
                print(f"    {line}")
                lines.append(line)
    except serial.SerialException as e:
        log(f"Error reading serial port: {e}")
        sys.exit(1)
    return lines


def capture_serial_after_reset(port, baud=115200, timeout=300, reset_cmd=None, settle_ms=200):
    log(f"Opening {port} at {baud} baud before reset...")
    lines = []
    pending = ""
    reset_proc = None

    try:
        with serial.Serial(port, baudrate=baud, timeout=1) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            if reset_cmd:
                time.sleep(settle_ms / 1000.0)
                log(f"Issuing reset while serial port is open: {reset_cmd}")
                reset_proc = subprocess.Popen(reset_cmd, shell=True)

            start = time.time()
            while time.time() - start < timeout:
                chunk = ser.read(ser.in_waiting or 1)
                if not chunk:
                    if reset_proc is not None:
                        ret = reset_proc.poll()
                        if ret is not None and ret != 0:
                            log(f"Reset command failed with exit code {ret}")
                            sys.exit(1)
                    continue

                text = chunk.decode("utf-8", errors="replace")
                pending += text

                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line:
                        continue
                    print(f"    {line}")
                    lines.append(line)
                    if "ORBIT benchmark completed" in line:
                        if reset_proc is not None:
                            ret = reset_proc.wait(timeout=5)
                            if ret != 0:
                                log(f"Reset command failed with exit code {ret}")
                                sys.exit(1)
                        log("Benchmark complete signal received")
                        return lines

            if pending.strip():
                line = pending.rstrip("\r")
                print(f"    {line}")
                lines.append(line)
            if reset_proc is not None:
                ret = reset_proc.wait(timeout=5)
                if ret != 0:
                    log(f"Reset command failed with exit code {ret}")
                    sys.exit(1)
    except serial.SerialException as e:
        log(f"Error reading serial port: {e}")
        sys.exit(1)
    return lines


def capture_local_process(binary_path, timeout=300):
    log(f"Running local benchmark binary: {binary_path}")
    lines = []

    try:
        with subprocess.Popen(
            [binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            start = time.time()
            assert proc.stdout is not None

            while True:
                if time.time() - start > timeout:
                    proc.kill()
                    log("Local benchmark timed out")
                    sys.exit(1)

                line = proc.stdout.readline()
                if line:
                    clean = line.rstrip("\r\n")
                    if clean:
                        print(f"    {clean}")
                        lines.append(clean)
                        if "ORBIT benchmark completed" in clean:
                            break
                    continue

                if proc.poll() is not None:
                    break

            ret = proc.wait(timeout=5)
            if ret != 0:
                log(f"Local benchmark exited with code {ret}")
                sys.exit(1)
    except OSError as e:
        log(f"Error running local benchmark: {e}")
        sys.exit(1)

    return lines

def save_results(lines, output_path, run_index, total_runs, board, algo, memory_metrics=None):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    header_to_write = DEFAULT_CSV_HEADER
    fieldnames = next(csv.reader([header_to_write]))
    field_index = {name: idx for idx, name in enumerate(fieldnames)}
    timestamp_re = re.compile(r"(1970-\d\d-\d\dT\d\d:\d\d:\d\dZ|\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)")

    data_rows = []
    require_start_marker = board in {"stm32"}
    saw_benchmark_start = not require_start_marker
    for line in lines:
        if "ORBIT benchmark starting" in line:
            saw_benchmark_start = True
            continue
        if not saw_benchmark_start:
            continue

        match = timestamp_re.search(line)
        if match:
            line = line[match.start():]
            ts_now = host_timestamp_iso()
            try:
                parsed = next(csv.reader([line]))
            except StopIteration:
                continue
            
            if len(parsed) < 2:
                continue
            if len(parsed) < len(fieldnames):
                log(f"Skipping short CSV row with {len(parsed)} field(s): {line[:80]}")
                continue
            if len(parsed) > len(fieldnames):
                extra = parsed[len(fieldnames):]
                if any(value.strip() for value in extra):
                    log(
                        f"Skipping contaminated CSV row with {len(parsed)} field(s); "
                        f"expected {len(fieldnames)}: {line[:120]}"
                    )
                    continue
                log(f"Trimming trailing empty CSV fields from {len(parsed)} to {len(fieldnames)} fields")
                parsed = parsed[:len(fieldnames)]

            if parsed[field_index["algorithm"]] != algo:
                log(
                    f"Skipping CSV row for unexpected algorithm "
                    f"{parsed[field_index['algorithm']]!r}; expected {algo!r}"
                )
                continue
            if parsed[field_index["board"]] != board:
                log(
                    f"Skipping CSV row for unexpected board "
                    f"{parsed[field_index['board']]!r}; expected {board!r}"
                )
                continue
            if parsed[field_index["ok"]] not in {"0", "1"}:
                log(f"Skipping CSV row with invalid ok field: {line[:120]}")
                continue
            
            parsed[0] = ts_now
            parsed[1] = make_run_id(ts_now, algo, board, parsed[6] if len(parsed) > 6 else "unknown")
            if memory_metrics:
                flash_idx = field_index.get("flash_bytes")
                ram_idx = field_index.get("ram_bytes")
                stack_idx = field_index.get("stack_bytes_peak")
                if flash_idx is not None and flash_idx < len(parsed):
                    parsed[flash_idx] = str(memory_metrics.get("flash_bytes", 0))
                if ram_idx is not None and ram_idx < len(parsed):
                    parsed[ram_idx] = str(memory_metrics.get("ram_bytes", 0))
                if stack_idx is not None and stack_idx < len(parsed):
                    parsed[stack_idx] = str(memory_metrics.get("stack_bytes_peak", 0))

            buf = io.StringIO()
            csv.writer(buf).writerow(parsed)
            data_rows.append(f"{run_index},{buf.getvalue().strip()}")
    
    if not data_rows:
        log("Warning: No data rows found in serial output.")
        return False
    
    write_header = (run_index == 1) and not os.path.exists(output_path)
    with open(output_path, "a", encoding="utf-8", newline="") as f:
        if write_header:
            f.write(f"run,{header_to_write}\n")
        for row in data_rows:
            f.write(f"{row}\n")
    
    log(f"Run {run_index}/{total_runs} results saved to {output_path}")
    return True


def run_one_benchmark(args, algo, output_path):
    board_info = BOARDS[args.board]

    if not args.build_only and args.archive_existing:
        archive_existing_result(output_path)

    log(f"Board:      {board_info['name']}")
    log(f"Algorithm:  {algo}")
    log(f"Runs:       {args.runs}")
    log(f"Output CSV: {output_path}")

    binary = build(
        args.board,
        algo,
        clean=args.clean,
        energy_runs=args.energy_runs,
        no_stdio_wait=args.no_stdio_wait,
    )
    memory_metrics = extract_memory_metrics(args.board, algo, binary)

    if args.build_only:
        log("Build-only mode enabled; skipping flashing and serial capture.")
        return

    slow_algos = {"aes_128_gcm", "ml_kem_512"}
    serial_timeout = 3600 if algo in slow_algos else 300

    for run in range(1, args.runs + 1):
        log(f"=== Starting run {run}/{args.runs} ===")

        if args.board == "rpi5":
            if args.flash and run == 1:
                log("RPi5 runs locally; ignoring --flash.")
            lines = capture_local_process(binary, timeout=serial_timeout)
            save_results(lines, output_path, run, args.runs, args.board, algo, memory_metrics=memory_metrics)
            continue

        port = args.port

        if args.flash:
            if args.board == "pico":
                flash_pico_for_run(binary, run)
            elif args.board == "stm32":
                if run == 1:
                    log("Run 1 will flash STM32 via OpenOCD and then capture serial output.")
                else:
                    log(f"Run {run}: reflashing STM32 to restart the benchmark...")
                FLASH_FUNCS[args.board](binary)
            elif args.board == "nrf52":
                if run == 1:
                    log("Run 1 will flash nRF52 via nrfjprog and then capture serial output.")
                else:
                    log(f"Run {run}: reflashing nRF52 to restart the benchmark...")
                FLASH_FUNCS[args.board](binary)
            elif args.board in IDF_BOARDS:
                if port is None:
                    port = find_serial_port(timeout=20)
                if port is None:
                    log("ERROR: Could not find serial port - exiting")
                    sys.exit(1)
                if run == 1:
                    log(f"Run 1 will flash {board_info['name']} via ESP-IDF and then capture serial output.")
                else:
                    log(f"Run {run}: reflashing {board_info['name']} to restart the benchmark...")
                flash_idf(args.board, algo, port=port)
            else:
                log(f"Auto-flash not yet implemented for {board_info['name']}")
                log(f"Please flash manually: {binary}")
                input("Press Enter when the board is running the new firmware ...")
        else:
            if run == 1:
                log("Manual flash mode - please flash the board now")
                log(f"Binary to flash: {binary}")
                log("Flash the binary now, then come back here.")
                input("Press Enter when the board is flashed and ready...")
            else:
                log("Reflash or reset the board for the next run:")
                if args.board == "pico":
                    log("  Pico: put the board in BOOTSEL mode, copy the UF2, then let it reboot")
                elif args.board == "stm32":
                    log("  STM32: flash/reset the board so the benchmark restarts from reset")
                elif args.board in IDF_BOARDS:
                    log("  ESP-IDF: flash/reset the board so the benchmark restarts from reset")
                log(f"  Artifact: {binary}")
                input("Press Enter when the board is flashed and ready...")

        port = port or find_serial_port(timeout=20)
        if port is None:
            log("ERROR: Could not find serial port - exiting")
            sys.exit(1)

        if args.board == "stm32":
            lines = capture_serial_after_reset(
                port,
                baud=BOARDS[args.board]["baud"],
                timeout=serial_timeout,
                reset_cmd=stm32_reset_cmd(),
            )
        elif args.board == "nrf52":
            lines = capture_serial_after_reset(
                port,
                baud=BOARDS[args.board]["baud"],
                timeout=serial_timeout,
                reset_cmd="nrfjprog --reset -f nrf52",
            )
        else:
            lines = capture_serial(port, baud=BOARDS[args.board]["baud"], timeout=serial_timeout)
        save_results(lines, output_path, run, args.runs, args.board, algo, memory_metrics=memory_metrics)

    log(f"\nAll {args.runs} runs complete for {algo}:")
    log(f"Results saved to: {output_path}")

    if os.path.exists(output_path):
        postprocess_csv(output_path)
    else:
        log("No results CSV was created, so post-processing was skipped.")


def parse_suite_algorithms(value):
    if not value:
        return list(ALGORITHMS)

    selected = []
    for raw in value.split(","):
        algo = raw.strip()
        if not algo:
            continue
        if algo not in ALGORITHMS:
            log(f"Unknown algorithm in --suite-algos: {algo}")
            log(f"Available algorithms: {', '.join(ALGORITHMS)}")
            sys.exit(1)
        selected.append(algo)

    if not selected:
        log("--suite-algos did not contain any valid algorithms")
        sys.exit(1)
    return selected


def output_path_for(args, algo, suite_count):
    if args.output is None:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        return os.path.join(RESULTS_DIR, f"{args.board}_{algo}.csv")

    if suite_count <= 1:
        return args.output

    base, ext = os.path.splitext(args.output)
    return f"{base}_{algo}{ext or '.csv'}"

# ----- Main -----
def main():
    parser = argparse.ArgumentParser(
        description="ORBIT Benchmark Orchestration Tool", 
        formatter_class=argparse.RawDescriptionHelpFormatter,         
        epilog="""
Examples:
  # Interactive mode (prompts for board and algo):
  python3 tools/orbit.py
 
  # Explicit run with auto-flash:
  python3 tools/orbit.py --board pico --algo ascon_aead128 --runs 5 --flash
 
  # Fix timestamps in an existing CSV produced without host-side injection:
  python3 tools/orbit.py --postprocess results/pico_ascon_aead128.csv
        """,
    )
    parser.add_argument("--board", required=False, choices=BOARDS.keys(), help="Target board")
    parser.add_argument("--algo", required=False, choices=ALGORITHMS, help="Algorithm to benchmark")
    parser.add_argument("--suite", action="store_true", help="Run the full algorithm suite for the selected board")
    parser.add_argument("--suite-algos", default=None, help="Comma-separated algorithm list for --suite (default: all supported algorithms)")
    parser.add_argument("--pause-between-algos", action="store_true", help="Pause between suite algorithms for WaveForms setup")
    parser.add_argument("--runs", type=int, default=5, help="Number of independent runs (default: 5)")
    parser.add_argument("--output", default=None, help="Output CSV file path (default: results/<board>_<algo>.csv)")
    parser.add_argument("--archive-existing", action="store_true",
                        help="Archive an existing output CSV before writing a new one")
    parser.add_argument("--flash", action="store_true", help="Automatically flash the firmware after building")
    parser.add_argument("--build-only", action="store_true", help="Build firmware and exit without flashing or capturing serial output")
    parser.add_argument("--energy-runs", type=int, default=None, help="Build firmware that repeats the benchmark this many times internally, with one frame trigger per internal run")
    parser.add_argument("--no-stdio-wait", action="store_true", help="Build firmware that starts without waiting for a USB/serial connection")
    parser.add_argument("--check", action="store_true", help="Check local prerequisites for Pico/STM32 workflows and exit")
    parser.add_argument("--clean", action="store_true", help="Clean build directory before building")
    parser.add_argument("--port", default=None, help="Serial port to use for capturing results (default: auto-detect)")
    parser.add_argument("--postprocess", metavar="CSV", help="Post-process an existing CSV file to fix timestamps and run IDs")
    args = parser.parse_args()

    if args.postprocess:
        postprocess_csv(args.postprocess)
        return

    if args.check:
        sys.exit(run_prereq_check(board=args.board))

    if args.energy_runs is not None and args.energy_runs < 1:
        log("--energy-runs must be at least 1")
        sys.exit(1)

    if not args.board or (not args.algo and not args.suite):
        print("\n=== ORBIT Interactive Mode ===")

        if not args.board:
            print("Available boards:")
            for i, (key, val) in enumerate(BOARDS.items(), 1):
                print(f"  [{i}] {key} - {val['name']}")
            while True:
                choice = input("Select a board: ").strip()
                board_keys = list(BOARDS.keys())
                if choice.isdigit() and 1 <= int(choice) <= len(BOARDS):
                    args.board = board_keys[int(choice) - 1]
                    break
                elif choice in BOARDS:
                    args.board = choice
                    break
                print("Invalid choice, please try again.")

        if not args.algo and not args.suite:
            print("\nAvailable algorithms:")
            for i, algo in enumerate(ALGORITHMS, 1):
                print(f"  [{i}] {algo}")
            while True:
                choice = input("Select an algorithm: ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(ALGORITHMS):
                    args.algo = ALGORITHMS[int(choice) - 1]
                    break
                elif choice in ALGORITHMS:
                    args.algo = choice
                    break
                print("Invalid choice, please try again.")
        
        if args.runs == 5:
            runs_input = input("\nEnter number of runs (default 5): ").strip()
            if runs_input.isdigit():
                args.runs = int(runs_input)

    algorithms = parse_suite_algorithms(args.suite_algos) if args.suite else [args.algo]
    pause_between_algos = args.pause_between_algos or args.suite

    for index, algo in enumerate(algorithms, 1):
        if args.suite:
            log(f"=== Suite algorithm {index}/{len(algorithms)}: {algo} ===")

        output_path = output_path_for(args, algo, len(algorithms))
        run_one_benchmark(args, algo, output_path)

        if pause_between_algos and index < len(algorithms) and not args.build_only:
            next_algo = algorithms[index]
            log(f"Completed {algo}.")
            log(f"Set up WaveForms for {next_algo}, arm the trigger, then return here.")
            input("Press Enter to build/flash and start the next algorithm ...")

    if args.suite:
        log("Full suite complete.")

    
if __name__ == "__main__":
    main()
