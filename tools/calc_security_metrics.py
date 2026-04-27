#!/usr/bin/env python3
"""Derive security-normalized efficiency metrics from ORBIT summary CSV files.

This script computes security bits per cycle and security bits per microjoule
from aggregate summary rows. It is intended for appendix-ready derived metrics,
not as a replacement for raw timing or energy analysis.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_SUMMARY_DIR = Path("results/summary")
DEFAULT_OUTPUT = DEFAULT_SUMMARY_DIR / "security_metrics.csv"
DEFAULT_CLASSICAL_OUTPUT = DEFAULT_SUMMARY_DIR / "security_metrics_classical.csv"
DEFAULT_QUANTUM_OUTPUT = DEFAULT_SUMMARY_DIR / "security_metrics_quantum.csv"

AEAD_ALGOS = {"ascon_aead128", "ascon_aead80pq", "gift_cofb", "aes_128_gcm"}

ALGO_LABELS = {
    "ascon_aead128": "Ascon-AEAD128",
    "ascon_aead80pq": "Ascon-80pq",
    "gift_cofb": "GIFT-COFB",
    "aes_128_gcm": "AES-128-GCM",
    "ml_kem_512": "ML-KEM-512",
}

BOARD_LABELS = {
    "esp32c61": "ESP32-C61",
    "stm32": "STM32 F446RE",
    "pico": "RP2040 Pico",
    "nrf52": "nRF52840 DK",
    "rpi5": "Raspberry Pi 5",
}

# These are normalization assumptions, not measured security values.
SECURITY_PROFILES = {
    "aes_128_gcm": [
        {
            "family": "classical",
            "basis": "classical_128",
            "bits": 128,
            "note": "AES-128 security strength normalization.",
        },
        {
            "family": "quantum",
            "basis": "grover_64",
            "bits": 64,
            "note": (
                "Grover-style exhaustive-key-search normalization for a 128-bit "
                "symmetric key."
            ),
        },
    ],
    "ascon_aead128": [
        {
            "family": "classical",
            "basis": "classical_128",
            "bits": 128,
            "note": "Ascon-AEAD128 normalized to 128-bit security strength.",
        },
        {
            "family": "quantum",
            "basis": "grover_64",
            "bits": 64,
            "note": (
                "Grover-style exhaustive-key-search normalization for "
                "Ascon-AEAD128."
            ),
        },
    ],
    "gift_cofb": [
        {
            "family": "classical",
            "basis": "classical_128",
            "bits": 128,
            "note": "GIFT-COFB normalized to a 128-bit AEAD security target.",
        },
        {
            "family": "quantum",
            "basis": "grover_64",
            "bits": 64,
            "note": (
                "Grover-style exhaustive-key-search normalization for GIFT-COFB "
                "under a 128-bit symmetric-key assumption."
            ),
        },
    ],
    "ascon_aead80pq": [
        {
            "family": "classical",
            "basis": "classical_128",
            "bits": 128,
            "note": (
                "Classical-security normalization for Ascon-80pq. The 160-bit key "
                "does not imply a 160-bit classical claim; the original Ascon "
                "security claim remains 128-bit against classical attacks."
            ),
        },
        {
            "family": "quantum",
            "basis": "grover_80",
            "bits": 80,
            "note": (
                "Grover-style exhaustive-key-search normalization for Ascon-80pq "
                "(160-bit key interpreted as roughly 80-bit exhaustive-search "
                "resistance under Grover's algorithm)."
            ),
        },
    ],
    "ml_kem_512": [
        {
            "family": "classical",
            "basis": "nist_cat1_aes128eq",
            "bits": 128,
            "note": (
                "ML-KEM-512 normalized to NIST Category 1, treated as an "
                "AES-128-equivalent security target for comparison."
            ),
        }
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate security-normalized metrics from ORBIT summary CSVs."
    )
    parser.add_argument(
        "--summary_files",
        nargs="*",
        help="Explicit summary CSV files. Defaults to results/summary/*_summary.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--msg_len",
        type=int,
        default=None,
        help=(
            "Optional AEAD message-length filter. If omitted, all AEAD message sizes "
            "and all ML-KEM operations are included."
        ),
    )
    parser.add_argument(
        "--classical_output",
        type=Path,
        default=DEFAULT_CLASSICAL_OUTPUT,
        help=f"Classical/standardized-only output CSV (default: {DEFAULT_CLASSICAL_OUTPUT})",
    )
    parser.add_argument(
        "--quantum_output",
        type=Path,
        default=DEFAULT_QUANTUM_OUTPUT,
        help=f"Quantum-adjusted output CSV (default: {DEFAULT_QUANTUM_OUTPUT})",
    )
    return parser.parse_args()


def discover_summary_files(explicit: list[str] | None) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    return sorted(DEFAULT_SUMMARY_DIR.glob("*_summary.csv"))


def safe_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_rows(paths: list[Path], msg_len_filter: int | None) -> list[dict[str, object]]:
    output_rows: list[dict[str, object]] = []

    for path in paths:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                board = row["board"]
                algorithm = row["algorithm"]
                operation = row["operation"]
                msg_len = int(row["msg_len"] or 0)

                if algorithm in AEAD_ALGOS:
                    if operation != "aead":
                        continue
                    if msg_len_filter is not None and msg_len != msg_len_filter:
                        continue
                elif algorithm == "ml_kem_512":
                    if operation not in {"keygen", "encap", "decap"}:
                        continue
                else:
                    continue

                cycles_total = safe_float(row["enc_cycles_total_mean"])
                energy_per_op = safe_float(row["energy_uJ_per_op_enc_mean"])
                latency_per_op = safe_float(row["enc_time_us_per_op_mean"])

                if cycles_total is None or cycles_total <= 0:
                    continue

                for profile in SECURITY_PROFILES.get(algorithm, []):
                    bits = profile["bits"]
                    bits_per_cycle = bits / cycles_total
                    bits_per_uj = (
                        bits / energy_per_op if energy_per_op is not None and energy_per_op > 0 else None
                    )

                    output_rows.append(
                        {
                            "board": board,
                            "board_label": BOARD_LABELS.get(board, board),
                            "algorithm": algorithm,
                            "algorithm_label": ALGO_LABELS.get(algorithm, algorithm),
                            "operation": operation,
                            "msg_len": msg_len,
                            "security_family": profile["family"],
                            "security_basis": profile["basis"],
                            "security_bits": bits,
                            "latency_us_per_op_mean": latency_per_op,
                            "cycles_total_mean": cycles_total,
                            "energy_uJ_per_op_mean": energy_per_op,
                            "security_bits_per_cycle": bits_per_cycle,
                            "security_bits_per_uJ": bits_per_uj,
                            "assumption_note": profile["note"],
                            "source_file": str(path),
                        }
                    )

    return output_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "board",
        "board_label",
        "algorithm",
        "algorithm_label",
        "operation",
        "msg_len",
        "security_family",
        "security_basis",
        "security_bits",
        "latency_us_per_op_mean",
        "cycles_total_mean",
        "energy_uJ_per_op_mean",
        "security_bits_per_cycle",
        "security_bits_per_uJ",
        "assumption_note",
        "source_file",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    summary_files = discover_summary_files(args.summary_files)
    if not summary_files:
        raise SystemExit("No summary CSV files found.")

    rows = load_rows(summary_files, args.msg_len)
    if not rows:
        raise SystemExit("No matching rows found in summary CSV files.")

    write_csv(args.output, rows)

    classical_rows = [row for row in rows if row["security_family"] == "classical"]
    quantum_rows = [row for row in rows if row["security_family"] == "quantum"]

    write_csv(args.classical_output, classical_rows)
    write_csv(args.quantum_output, quantum_rows)

    print(f"[security] Wrote {len(rows)} row(s) to {args.output}")
    print(f"[security] Wrote {len(classical_rows)} classical row(s) to {args.classical_output}")
    print(f"[security] Wrote {len(quantum_rows)} quantum-adjusted row(s) to {args.quantum_output}")
    print("[security] Assumptions are included in the output CSVs under assumption_note.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
