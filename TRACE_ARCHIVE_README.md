# ORBIT Trace Archive

This archive contains the full per-run waveform-aligned trace datasets generated for ORBIT:

**ORBIT: Open-Source Reference Benchmark for IoT Cryptography**

The trace files are hosted separately from the main GitHub repository because several datasets exceed GitHub's recommended and enforced file size limits.

## Archive scope

This archive is intended to accompany the ORBIT repository and the associated M.Eng. Project & Report:

- thesis/repo topic: cross-architecture benchmarking of lightweight and post-quantum cryptography on constrained IoT platforms
- repository: `https://github.com/Ethancd19/ORBIT`
- Zenodo DOI: `https://doi.org/10.5281/zenodo.19804002`
- archive type: full per-run trace datasets

## Contents

The archive is expected to include:

- full CSV trace exports from `results/traces/`
- one file per board/algorithm combination
- five-run benchmark trace collections where applicable

Typical file naming pattern:

```text
<board>_<algorithm>_runs_1-5.csv
```

Examples:

```text
esp32c61_ascon128_runs_1-5.csv
nrf52_ascon_aead128_runs_1-5.csv
pico_aes_128_gcm_runs_1-5.csv
stm32_ml_kem_512_runs_1-5.csv
```

## Boards represented

- `pico`      : Raspberry Pi Pico (RP2040)
- `stm32`     : STM32 Nucleo F446RE
- `nrf52`     : Nordic nRF52840 DK (PCA10056)
- `esp32c61`  : ESP32-C61

## Algorithms represented

- `ascon_aead128`
- `ascon_aead80pq`
- `gift_cofb`
- `aes_128_gcm`
- `ml_kem_512`

Note: some filenames may use the shorter `ascon128` form depending on the collection workflow used when exporting traces.

## How the traces relate to ORBIT results

These trace files support the externally captured energy-measurement workflow used in ORBIT. They are intended to correspond to:

- top-level benchmark CSVs in `results/`
- summary outputs in `results/summary/`
- energy post-processing performed with `tools/process_energy.py`

For long externally captured runs, ORBIT can be built with `--energy-runs <N>` so that the firmware emits one frame trigger per internal run. This makes it possible to align a longer WaveForms capture against the matching ORBIT CSV rows during post-processing.

## Provenance

- ORBIT commit hash associated with this dataset: `dd563662fa263caf7fd0a7c0592f4c5b1cb87b74`
- archive creation date: `2026-04-26`
- WaveForms export source: `WaveForms Record-to-File CSV exports from Analog Discovery 3 captures aligned with ORBIT GPIO trigger windows`
- excluded files: `None`

## Notes

- These traces are not committed to the main GitHub repository due to file size limits.
- The GitHub repository remains the source of truth for code, benchmark orchestration, processed result CSVs, and summary outputs.
- This archive exists to preserve the larger raw trace artifacts needed for full energy-measurement reproducibility.
