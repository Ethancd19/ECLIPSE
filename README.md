# ORBIT

## Open-Source Reference Benchmark for IoT Cryptography

ORBIT is a portable bare-metal C benchmarking framework for evaluating lightweight and post-quantum cryptographic algorithms on constrained IoT platforms. It measures performance (cycles/byte), energy consumption ($\mu$J/operation), and memory footprint across multiple embedded architectures under identical, reproducible conditions.

Developed as a part of an M.Eng. Project & Report in Computer Engineering at Virginia Polytechnic Institute and State University, 2026.

---

## Algorithms

| Algorithm     | Type | Standard / Status    | Notes                                 |
| ------------- | ---- | -------------------- | ------------------------------------- |
| Ascon-AEAD128 | AEAD | NIST SP 800-232      | Primary lightweight benchmark         |
| Ascon-80pq    | AEAD | Ascon family variant | PQ-oriented symmetric hedge           |
| GIFT-COFB     | AEAD | NIST LWC Finalist    | SPN-based, compact hardware footprint |
| AES-128-GCM   | AEAD | NIST SP 800-38D      | Baseline industry standard            |
| ML-KEM-512    | KEM  | FIPS 203             | Post-quantum key encapsulation        |

All algorithms use publicly available reference C implementations. Hardware acceleration is explicitly disabled on all platforms for cross-architecture comparability.

---

## Hardware Platforms

| Board                         | MCU       | Architecture    | Clock   | RAM    | Flash  |
| ----------------------------- | --------- | --------------- | ------- | ------ | ------ |
| Raspberry Pi Pico             | RP2040    | ARM Cortex-M0+  | 125 MHz | 264 KB | 2 MB   |
| STM32 Nucleo F446RE           | STM32F446 | ARM Cortex-M4F  | 180 MHz | 128 KB | 512 KB |
| Nordic nRF52840 DK (PCA10056) | nRF52840  | ARM Cortex-M4F  | 64 MHz  | 256 KB | 1 MB   |
| ESP32-C61                     | ESP32-C61 | RISC-V RV32IMAC | 160 MHz | 512 KB | 4 MB   |
| Raspberry Pi 5                | BCM2712   | ARM Cortex-A76  | 2.4 GHz | 8 GB   | -      |

---

## Repository Structure

```text
ORBIT/
├── algorithms/
│   ├── ascon_aead128/      # Ascon-128 reference (NIST SP 800-232)
│   ├── ascon_aead80pq/     # Ascon-80pq reference
│   ├── gift_cofb/          # GIFT-COFB opt32 (NIST LWC finalist)
│   ├── aes_128_gcm/        # AES-128-GCM (cifra library, software-only)
│   └── ml_kem_512/         # ML-KEM-512 (PQClean reference, FIPS 203)
├── bench/
│   ├── main.c              # Benchmark loop, KAT correctness checks
│   ├── util.c / util.h     # CSV output, statistics, timing utilities
│   └── platform.h          # Resolved from platforms/<board>/platform.h
├── platforms/
│   ├── pico/platform.h     # RP2040: SysTick + time_us_64 cycle counter
│   ├── stm32/platform.h    # STM32F446: DWT CYCCNT cycle counter
│   ├── nrf52/platform.h    # nRF52840 DK: TIMER1-based cycle counter
│   ├── esp32c61/           # ESP32-C61: ESP-IDF target support
│   └── rpi5/platform.h     # RPi5: native Linux timer/counter backend
├── results/
│   ├── archived/           # Preliminary single-run data (superseded)
│   └── *.csv               # Final 5-run benchmark datasets
├── scripts/
│   └── attach_pico.ps1     # Windows: auto-attach Pico to WSL2 via usbipd
├── tools/
│   ├── orbit.py            # Benchmark orchestration and serial capture
│   └── plot_results.py     # Result visualization
├── include/
│   └── crypto_aead.h       # Shared AEAD interface
├── CMakeLists.txt          # Pico SDK build (ARM targets)
├── setup.sh                # One-shot environment setup script
└── requirements.txt        # Python dependencies
```

---

## Host Environment Setup

> **These instructions target Windows 11 + WSL2 (Ubuntu 24.04 LTS).**
> Native Linux users can skip the WSL2 and usbipd sections.
> See the [Native Linux Notes](#native-linux-notes) section at the bottom.

### Requirements

- Windows 11 with WSL2 enabled
- Ubuntu 24.04 LTS under WSL2
- Python 3.12+
- USB port for board connection

---

### Step 1: Install usbipd-win (Windows side, once only)

usbipd-win forwards USB devices from Windows into WSL2.

Download and install from: **https://github.com/dorssel/usbipd-win/releases**

Then allow running local Powershell scripts (run PowerShell as Administrator, once only):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Step 2: Run the automated setup script (WSL2 side)

```bash
git clone https://github.com/ethancd19/ORBIT.git
cd ORBIT
chmod +x setup.sh
./setup.sh
```

This handles everything automatically:

- Ubuntu packages for ORBIT's ARM board workflows (`cmake`, `gcc-arm-none-eabi`, `openocd`, `build-essential`, `libusb`, etc.)
- Pico SDK clone and submodule init at `~/pico-sdk` with `PICO_SDK_PATH` added to `~/.bashrc`
- STM32CubeF4 clone and submodule init at `~/stm32cubeF4` with `STM32CUBE_F4_PATH` added to `~/.bashrc`
- Records `NRF5_SDK_PATH` in `~/.bashrc` and checks for Nordic host tools if you already installed them
- picotool build/install to `~/.local`, plus udev rules
- Python virtual environment at `.venv/` with all dependencies installed
- Passwordless sudo rule for `mount`/`umount` at `/etc/sudoers.d/orbit`
- `/mnt/pico` mount point

The build system looks for STM32CubeF4 at `~/stm32cubeF4` by default. Override with:

```bash
export STM32CUBE_F4_PATH=/path/to/STM32CubeF4
```

The nRF52 build looks for the Nordic nRF5 SDK at `~/nRF5_SDK` by default. Override with:

```bash
export NRF5_SDK_PATH=/path/to/nRF5_SDK
```

---

### Step 3: Activate the virtual environment

```bash
source .venv/bin/activate
```

To activate automatically on every terminal session, add to `~/.bashrc`:

```bash
echo 'cd ~/projects/ORBIT && source .venv/bin/activate' >> ~/.bashrc
```

---

### Step 4: Verify

```bash
source ~/.bashrc
source .venv/bin/activate

python3 tools/orbit.py --check
```

This verifies the toolchain and board-specific prerequisites used by ORBIT:

- `cmake`, `arm-none-eabi-gcc`, and Python
- `PICO_SDK_PATH`, `picotool`, `/mnt/pico`, and `attach_pico.ps1`
- `STM32CUBE_F4_PATH` and `openocd`
- `NRF5_SDK_PATH` and `nrfjprog`
- Visible USB serial devices such as `/dev/ttyACM0`

---

## Building

[orbit.py](tools/orbit.py) handles all building automatically. Build artifacts are placed in `build/` and are rebuilt automatically when switching boards or algorithms.

To build firmware without flashing or capturing serial output:

```bash
python3 tools/orbit.py --board pico --algo ascon_aead128 --build-only
```

Use `--clean` to force a clean rebuild when switching boards:

```bash
python3 tools/orbit.py --board stm32 --algo ascon_aead128 --runs 1 --clean
```

**Supported boards:** `pico`, `stm32`, `nrf52`, `esp32c61`, `rpi5`

**Supported algorithms:** `ascon_aead128`, `ascon_aead80pq`, `gift_cofb`, `aes_128_gcm`, `ml_kem_512`

### Board-specific dependencies

| Board       | Extra dependency            | How to install                                                                 |
| ----------- | --------------------------- | ------------------------------------------------------------------------------ |
| Pico        | Pico SDK                    | Handled by `setup.sh`                                                          |
| STM32       | STM32CubeF4                 | Handled by `setup.sh`; override with `STM32CUBE_F4_PATH` if needed             |
| nRF52840 DK | nRF5 SDK + Nordic CLI tools | Install the nRF5 SDK, `nrfjprog`, and Segger J-Link tools; set `NRF5_SDK_PATH` |
| ESP32-C61   | ESP-IDF v5.x                | Install ESP-IDF and use the `esp32c61` target support in `tools/orbit.py`      |
| RPi5        | Native Linux toolchain      | `sudo apt install build-essential cmake python3 python3-venv`                  |

---

## Running Benchmarks

Before the first run on a new machine:

```bash
source ~/.bashrc
source .venv/bin/activate
python3 tools/orbit.py --check
```

### Automated mode (recommended for USB-attached boards)

```bash
source .venv/bin/activate

python3 tools/orbit.py \
  --board <board> \
  --algo <algorithm> \
  --runs 5 \
  --flash
```

Results save to `results/<board>_<algorithm>.csv`.

#### Pico example

```bash
python3 tools/orbit.py --board pico --algo ascon_aead128 --runs 5 --flash
```

#### STM32 example

```bash
python3 tools/orbit.py --board stm32 --algo ascon_aead128 --runs 5 --flash
```

> Each run automatically reflashes the board via OpenOCD and captures serial output.

#### RPi5 example

Run this directly on the Raspberry Pi 5 itself:

```bash
python3 tools/orbit.py --board rpi5 --algo ascon_aead128 --runs 5
```

The RPi5 target is a native Linux executable. ORBIT builds the binary locally, runs it on the Pi, captures stdout directly, and writes `results/rpi5_<algorithm>.csv`.

### Available flags

| Flag                    | Description                                                                                  |
| ----------------------- | -------------------------------------------------------------------------------------------- |
| `--board`               | Target board (`pico`, `stm32`, `nrf52`, `esp32c61`, `rpi5`)                                  |
| `--algo`                | Algorithm to benchmark                                                                       |
| `--runs`                | Independent runs (default: 5)                                                                |
| `--flash`               | Auto-flash firmware after build                                                              |
| `--build-only`          | Build firmware and exit without flashing or serial capture                                   |
| `--check`               | Verify local board prerequisites and exit                                                    |
| `--clean`               | Clean build directory first                                                                  |
| `--output`              | Custom output CSV path                                                                       |
| `--port`                | Serial port override (recommended when multiple USB serial devices exist)                    |
| `--energy-runs`         | Build firmware that repeats the benchmark internally with one frame trigger per internal run |
| `--suite`               | Run the full supported algorithm suite for the selected board                                |
| `--suite-algos`         | Comma-separated subset for `--suite` (default: all supported algorithms)                     |
| `--pause-between-algos` | Pause between suite algorithms to support external measurement setup                         |
| `--archive-existing`    | Archive an existing output CSV before writing a new one                                      |
| `--no-stdio-wait`       | Build firmware that starts without waiting for a USB/serial connection                       |
| `--postprocess CSV`     | Fix epoch timestamps in an existing CSV                                                      |

### Per-run workflow (Pico + WSL2)

**Run 1:** [orbit.py](tools/orbit.py) prompts you to put the Pico in BOOTSEL mode:

1. Hold the BOOTSEL button
2. Unplug the USB cable
3. Plug the USB cable back in
4. Release BOOTSEL
5. Press Enter in the WSL2 terminal when prompted

[orbit.py](tools/orbit.py) then automatically finds the device, attaches it via usbipd, mounts the drive at `/mnt/pico`, and copies the UF2.

**Runs 2–5:** [orbit.py](tools/orbit.py) attempts to reboot the Pico into BOOTSEL with `picotool`, re-attach it via `usbipd`, and remount `/mnt/pico` automatically.

If the auto-mount step fails, ORBIT falls back to prompting you for a manual mount:

```bash
lsblk
sudo mount -o rw,uid=$(id -u),gid=$(id -g) /dev/sdX1 /mnt/pico
```

### Per-run workflow (STM32 + WSL2)

The ST-LINK must be attached to WSL2 once before running [orbit.py](tools/orbit.py). In PowerShell:

```powershell
usbipd attach --wsl --busid <busid>
```

Find the busid with `usbipd list` (look for "STM32 STLink", VID:PID `0483:374b`).

After that, [orbit.py](tools/orbit.py) with `--flash` handles flashing via OpenOCD and captures serial output automatically for every run.

If OpenOCD needs a non-default interface or target config, override it before running:

```bash
export ORBIT_STM32_OPENOCD_CFG="interface/stlink.cfg -f target/stm32f4x.cfg"
```

If more than one USB serial device is visible in WSL2, pass the board port explicitly:

```bash
python3 tools/orbit.py --board stm32 --algo ascon_aead128 --runs 5 --flash --port /dev/ttyACM0
```

### Per-run workflow (nRF52 + WSL2)

The PCA10056 is flashed via `nrfjprog` and benchmark output is captured from the board's J-Link virtual COM port.

Before running:

1. Install the Nordic nRF5 SDK
2. Install Nordic Command Line Tools so `nrfjprog` is on `PATH`
3. Install Segger J-Link tools
4. Export `NRF5_SDK_PATH`
5. Attach the board to WSL2 if needed

For a full automated run, use:

```bash
python3 tools/orbit.py --board nrf52 --algo ascon_aead128 --runs 5 --flash --port /dev/ttyACM0
```

If two ACM ports appear, the validated capture port for the PCA10056 workflow is typically `/dev/ttyACM0`.

ORBIT handles:

- building the firmware
- flashing with `nrfjprog`
- opening the serial port before reset
- resetting the board again so the full benchmark output is captured from the top

### Manual flash mode

If you omit `--flash`, ORBIT still builds and captures results, but it waits for you to flash or reset the board yourself between runs.

### Native workflow (RPi5)

The Raspberry Pi 5 does not use USB flashing or serial capture. Instead:

1. SSH into the Raspberry Pi 5
2. Clone ORBIT directly onto the Pi
3. Install the native Linux prerequisites on the Pi, or run `./setup.sh`
4. Build and execute the benchmark locally on the Pi with `python3 tools/orbit.py --board rpi5 --algo <algorithm> --runs 5`

`--flash` is ignored for `rpi5` because there is no device flashing step.

### Fixing timestamps on existing CSVs

```bash
python3 tools/orbit.py --postprocess results/pico_ascon_aead128.csv
```

Uses the file modification time as a proxy for the actual run timestamp.

### Interactive mode

```bash
python3 tools/orbit.py
```

This will prompt you through the available boards and algorithms you can run.

---

## Energy Measurement

Energy measurements are collected at the board level using an Analog Discovery 3 and GPIO trigger windows emitted by the benchmark firmware.

### Hardware required

- Analog Discovery 3
- WaveForms host software
- Dedicated measurement wiring for each target board
- GPIO trigger connection from the target to the AD3 digital input

### Collection workflow

1. Prepare the board under test on a dedicated measurement setup.
2. Build and run the same firmware used for timing benchmarks.
3. Use GPIO trigger windows to mark the active measurement interval.
4. Capture the resulting waveform in WaveForms.
5. Export the trace and post-process it alongside the benchmark CSV output.

For AEAD algorithms, one trigger window covers the measured benchmark loop. For ML-KEM-512, KeyGen, Encapsulation, and Decapsulation are measured as separate operations.

### Energy capture mode

For externally captured energy measurements, ORBIT also supports:

```bash
python3 tools/orbit.py --board <board> --algo <algorithm> --runs 5 --flash --energy-runs <N>
```

This builds firmware that repeats the benchmark internally and emits one frame trigger per internal run. It is useful when aligning WaveForms captures against ORBIT CSV output, especially for multi-run energy collection workflows.

Exact current-measurement wiring differs slightly by board and measurement rig. ORBIT documents the software workflow here, while board-specific electrical setup should follow the target board documentation and the local measurement fixture used in the experiment.

### Energy trace post-processing

After exporting a WaveForms CSV, merge the measured energy windows back into the ORBIT benchmark CSV:

```bash
python3 tools/process_energy.py \
  --scope path/to/waveforms_capture.csv \
  --orbit results/pico_ascon_aead128.csv \
  --rate <sample_rate_hz> \
  --runs 1,2,3,4,5 \
  --multi-run-scope
```

For long captures produced with `--energy-runs`, one frame trigger is emitted per internal run so the exported scope file can be aligned against the matching ORBIT CSV rows.

---

## Output Format

One CSV row per (algorithm, platform, message size) per run, prefixed with a `run` index.

| Field                 | Description                                     |
| --------------------- | ----------------------------------------------- |
| `run`                 | Independent run index (1-5)                     |
| `timestamp_iso`       | UTC timestamp injected from host clock          |
| `algorithm`           | Algorithm name                                  |
| `board`               | Target platform identifier                      |
| `arch`                | Instruction set architecture                    |
| `freq_hz`             | Core clock frequency (Hz)                       |
| `msg_len`             | Plaintext length (bytes)                        |
| `iterations`          | Iterations for this configuration               |
| `enc_cycles_total`    | Total cycles across all iterations (encryption) |
| `enc_cycles_per_byte` | Cycles per plaintext byte (primary metric)      |
| `enc_time_us_per_op`  | Microseconds per encryption operation           |
| `energy_uJ_enc_total` | Total energy: Over the encryption window        |
| `avg_power_mW_enc`    | Average power draw during encryption            |
| `ok`                  | 1 = KAT passed, 0 = KAT failed                  |
| `notes`               | Any output notes made during benchmark          |

---

## Results

Final 5-run datasets: `results/<board>_<algo>.csv`

Per-board summaries: `results/summary/`

Security-normalized derived metrics:

- `results/summary/security_metrics_classical.csv`
- `results/summary/security_metrics_quantum.csv`

Full per-run trace datasets are generated locally in `results/traces/` but are not committed to GitHub because several files exceed GitHub's size limits.

Full per-run trace archive (Zenodo): `https://doi.org/<DOI>`

Preliminary single-run data (collected before the 5-run protocol): `results/archived/`

---

## Cycle Counting

| Platform           | Method                                                         | Resolution    |
| ------------------ | -------------------------------------------------------------- | ------------- |
| RP2040 (Pico)      | SysTick + time_us_64()                                         | 1 cycle       |
| STM32F446 (Nucleo) | DWT CYCCNT                                                     | 1 cycle       |
| nRF52840 DK        | TIMER1 capture scaled to 64 MHz-equivalent ticks               | ~4 CPU cycles |
| ESP32-C61          | RISC-V CSR `cycle`                                             | 1 cycle       |
| BCM2712 (RPi5)     | ARM generic timer (`cntvct_el0`) with `clock_gettime` fallback | ~1 tick       |

> The RP2040 Cortex-M0+ does not implement DWT CYCCNT. ORBIT uses SysTick combined with the RP2040 hardware timer for equivalent single-cycle resolution within each microsecond tick.

---

## Native Linux Notes

Running on native Linux (Ubuntu, Debian, etc.) without WSL2:

- Skip Step 1 entirely (usbipd-win is not needed)
- USB devices are directly accessible as `/dev/ttyACM0` etc.
- The Pico BOOTSEL drive mounts automatically on most distros
- `scripts/attach_pico.ps1` is not used. The PowerShell call in [orbit.py](tools/orbit.py)'s `flash_pico()` will silently fail but the manual mount fallback will still work
- picotool BOOTSEL reboot works identically
- The Raspberry Pi 5 should be run directly as its own native Linux host with `--board rpi5`
- Everything else is the same

---

## Citation

```text
Duval, E.C. (2026). Cross-Architecture Benchmarking of Lightweight and
Post-Quantum Cryptography on Constrained IoT Platforms.
M.Eng. Project & Report, Virginia Polyechnic Institute and State University
```

---

## License

MIT License - see [LICENSE](LICENSE)
