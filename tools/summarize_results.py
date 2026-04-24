#!/usr/bin/env python3
"""Audit ORBIT result files and write aggregate summary statistics."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


BOARDS = ["pico", "nrf52", "stm32", "esp32c61", "rpi5"]
ALGORITHMS = [
    "ascon_aead128",
    "ascon_aead80pq",
    "gift_cofb",
    "aes_128_gcm",
    "ml_kem_512",
]
AEAD_ALGORITHMS = [algo for algo in ALGORITHMS if algo != "ml_kem_512"]
AEAD_MSG_SIZES = [16, 64, 256, 1024, 4096, 16384]
KEM_OPS = ["keygen", "encap", "decap"]

NUMERIC_METRICS = [
    "iterations",
    "enc_cycles_total",
    "dec_cycles_total",
    "enc_cycles_per_byte",
    "dec_cycles_per_byte",
    "enc_time_us_total",
    "dec_time_us_total",
    "enc_time_us_per_op",
    "dec_time_us_per_op",
    "flash_bytes",
    "ram_bytes",
    "stack_bytes_peak",
    "energy_uJ_enc_total",
    "energy_uJ_dec_total",
    "energy_uJ_per_byte_enc",
    "energy_uJ_per_byte_dec",
    "avg_power_mW_enc",
    "avg_power_mW_dec",
]

DERIVED_METRICS = [
    "energy_uJ_per_op_enc",
    "energy_uJ_per_op_dec",
]

# Two-sided t critical values for 95% confidence intervals.
T_CRIT_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return list(default)
    return [part.strip() for part in value.split(",") if part.strip()]


def log_warning(warnings: list[str], message: str) -> None:
    warnings.append(message)
    print(f"[warn] {message}")


def result_path(results_dir: Path, board: str, algo: str, prefer_energy: bool) -> Path:
    base = results_dir / f"{board}_{algo}.csv"
    energy = results_dir / f"{board}_{algo}_energy.csv"
    if prefer_energy and energy.exists():
        return energy
    return base


def result_path_with_energy_status(results_dir: Path, board: str, algo: str, prefer_energy: bool) -> tuple[Path, bool]:
    base = results_dir / f"{board}_{algo}.csv"
    energy = results_dir / f"{board}_{algo}_energy.csv"
    if prefer_energy and energy.exists():
        return energy, True
    return base, False


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def int_value(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(row.get(key, "") or default)
    except ValueError:
        return default


def float_values(rows: list[dict[str, str]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        raw = row.get(key, "")
        if raw == "":
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def derived_float_values(rows: list[dict[str, str]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        iterations = int_value(row, "iterations", default=0)
        if iterations <= 0:
            continue

        if key == "energy_uJ_per_op_enc":
            total_key = "energy_uJ_enc_total"
        elif key == "energy_uJ_per_op_dec":
            total_key = "energy_uJ_dec_total"
        else:
            continue

        try:
            total = float(row.get(total_key, "") or 0.0)
        except ValueError:
            continue

        value = total / iterations
        if math.isfinite(value):
            values.append(value)
    return values


def ci95(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    sd = stdev(values)
    tcrit = T_CRIT_95.get(n - 1, 1.96)
    return tcrit * sd / math.sqrt(n)


def group_key(row: dict[str, str]) -> tuple[str, str, str, int, str]:
    board = row.get("board", "")
    algo = row.get("algorithm", "")
    notes = row.get("notes", "")
    if algo == "ml_kem_512" or notes in KEM_OPS:
        operation = notes or "kem_op"
        msg_len = 0
    else:
        operation = "aead"
        msg_len = int_value(row, "msg_len")
    return board, algo, operation, msg_len, notes


def summarize_group(rows: list[dict[str, str]]) -> dict[str, str]:
    first = rows[0]
    board, algo, operation, msg_len, notes = group_key(first)
    run_values = sorted({int_value(row, "run") for row in rows})

    summary: dict[str, str] = {
        "board": board,
        "algorithm": algo,
        "operation": operation,
        "msg_len": str(msg_len),
        "notes": notes,
        "n_rows": str(len(rows)),
        "n_runs": str(len(run_values)),
        "runs": " ".join(str(run) for run in run_values),
    }

    for metric in NUMERIC_METRICS:
        values = float_values(rows, metric)
        if not values:
            summary[f"{metric}_mean"] = ""
            summary[f"{metric}_sd"] = ""
            summary[f"{metric}_ci95"] = ""
            continue
        summary[f"{metric}_mean"] = f"{mean(values):.9g}"
        summary[f"{metric}_sd"] = f"{stdev(values):.9g}" if len(values) > 1 else "0"
        summary[f"{metric}_ci95"] = f"{ci95(values):.9g}"

    for metric in DERIVED_METRICS:
        values = derived_float_values(rows, metric)
        if not values:
            summary[f"{metric}_mean"] = ""
            summary[f"{metric}_sd"] = ""
            summary[f"{metric}_ci95"] = ""
            continue
        summary[f"{metric}_mean"] = f"{mean(values):.9g}"
        summary[f"{metric}_sd"] = f"{stdev(values):.9g}" if len(values) > 1 else "0"
        summary[f"{metric}_ci95"] = f"{ci95(values):.9g}"

    return summary


def expected_rows_for_run(rows: list[dict[str, str]], algo: str) -> dict[int, list[dict[str, str]]]:
    by_run: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_run[int_value(row, "run")].append(row)
    return dict(by_run)


def audit_file(
    path: Path,
    board: str,
    algo: str,
    rows: list[dict[str, str]],
    expected_runs: int,
    require_energy: bool,
    warnings: list[str],
) -> None:
    if not rows:
        log_warning(warnings, f"{path}: no data rows")
        return

    if any(row.get("ok") != "1" for row in rows):
        bad = sum(row.get("ok") != "1" for row in rows)
        log_warning(warnings, f"{path}: {bad} row(s) have ok != 1")

    by_run = expected_rows_for_run(rows, algo)
    expected_run_ids = set(range(1, expected_runs + 1))
    actual_run_ids = set(by_run)
    missing_runs = sorted(expected_run_ids - actual_run_ids)
    extra_runs = sorted(actual_run_ids - expected_run_ids)
    if missing_runs:
        log_warning(warnings, f"{path}: missing run(s): {missing_runs}")
    if extra_runs:
        log_warning(warnings, f"{path}: unexpected run index value(s): {extra_runs}")

    if len(actual_run_ids & expected_run_ids) != expected_runs:
        log_warning(warnings, f"{path}: expected {expected_runs} run(s), found {sorted(actual_run_ids)}")

    if algo in AEAD_ALGORITHMS:
        for run, run_rows in sorted(by_run.items()):
            msg_sizes = sorted({int_value(row, "msg_len") for row in run_rows})
            missing_msg_sizes = [size for size in AEAD_MSG_SIZES if size not in msg_sizes]
            if missing_msg_sizes:
                log_warning(warnings, f"{path}: run {run} missing AEAD message size(s): {missing_msg_sizes}")
            duplicates = len(run_rows) - len(msg_sizes)
            if duplicates:
                log_warning(warnings, f"{path}: run {run} has {duplicates} duplicate AEAD message row(s)")
    else:
        for run, run_rows in sorted(by_run.items()):
            ops = sorted({row.get("notes", "") for row in run_rows})
            missing_ops = [op for op in KEM_OPS if op not in ops]
            if missing_ops:
                log_warning(warnings, f"{path}: run {run} missing ML-KEM operation(s): {missing_ops}")

    if require_energy:
        energy_cols = ["energy_uJ_enc_total"]
        if algo in AEAD_ALGORITHMS:
            energy_cols.append("energy_uJ_dec_total")
        for col in energy_cols:
            zero_rows = [i + 2 for i, row in enumerate(rows) if float(row.get(col, "0") or 0) == 0.0]
            if zero_rows:
                log_warning(warnings, f"{path}: {col} is zero/unpopulated on CSV row(s): {zero_rows[:10]}")


def write_summary(path: Path, summaries: list[dict[str, str]]) -> None:
    if not summaries:
        print("[summary] No summaries to write.")
        return

    fixed = ["board", "algorithm", "operation", "msg_len", "notes", "n_rows", "n_runs", "runs"]
    metric_fields: list[str] = []
    for metric in NUMERIC_METRICS + DERIVED_METRICS:
        metric_fields.extend([f"{metric}_mean", f"{metric}_sd", f"{metric}_ci95"])

    fieldnames = fixed + metric_fields
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)
    print(f"[summary] Wrote {len(summaries)} aggregate row(s) to {path}")


def write_audit(path: Path, warnings: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        if warnings:
            for warning in warnings:
                f.write(f"{warning}\n")
        else:
            f.write("No audit warnings.\n")
    print(f"[audit] Wrote audit report to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit ORBIT result coverage and write aggregate summary statistics."
    )
    parser.add_argument("--results-dir", default="results", help="Directory containing ORBIT CSV files")
    parser.add_argument("--boards", default=None, help="Comma-separated board list (default: all expected boards)")
    parser.add_argument("--algos", default=None, help="Comma-separated algorithm list (default: all expected algorithms)")
    parser.add_argument("--runs", type=int, default=5, help="Expected independent runs per file (default: 5)")
    parser.add_argument("--output", default="results/summary/orbit_summary.csv", help="Output summary CSV path")
    parser.add_argument("--audit-output", default="results/summary/orbit_audit.txt", help="Output audit report path")
    parser.add_argument(
        "--prefer-energy",
        action="store_true",
        help="Use results/<board>_<algo>_energy.csv when present instead of the base CSV",
    )
    parser.add_argument(
        "--require-energy",
        action="store_true",
        help="Warn when expected energy columns are zero/unpopulated for all audited boards unless --energy-boards is set",
    )
    parser.add_argument(
        "--energy-boards",
        default=None,
        help="Comma-separated board list that must have populated energy data, e.g. esp32c61,stm32,nrf52. Boards not listed are audited as timing-only.",
    )
    parser.add_argument(
        "--no-require-energy",
        action="store_true",
        help="Disable energy-field warnings even when --require-energy or --energy-boards is provided.",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    boards = parse_csv_list(args.boards, BOARDS)
    algos = parse_csv_list(args.algos, ALGORITHMS)
    energy_boards = set(parse_csv_list(args.energy_boards, []))
    require_all_energy = args.require_energy and not energy_boards and not args.no_require_energy
    warnings: list[str] = []
    all_rows: list[dict[str, str]] = []

    for board in boards:
        board_files_found = 0
        for algo in algos:
            path, using_energy_file = result_path_with_energy_status(results_dir, board, algo, args.prefer_energy)
            if not path.exists():
                log_warning(warnings, f"Missing result file: {path}")
                continue

            board_files_found += 1
            rows = load_rows(path)
            board_requires_energy = (
                not args.no_require_energy
                and (require_all_energy or board in energy_boards)
            )
            if board_requires_energy and args.prefer_energy and not using_energy_file:
                log_warning(warnings, f"{board}/{algo}: expected energy result file, found timing-only file: {path}")
            audit_file(path, board, algo, rows, args.runs, board_requires_energy, warnings)
            all_rows.extend(rows)

        if board_files_found != len(algos):
            log_warning(
                warnings,
                f"{board}: expected {len(algos)} algorithm file(s), found {board_files_found}",
            )

    groups: dict[tuple[str, str, str, int, str], list[dict[str, str]]] = defaultdict(list)
    for row in all_rows:
        groups[group_key(row)].append(row)

    summaries = [summarize_group(rows) for _, rows in sorted(groups.items())]
    write_summary(Path(args.output), summaries)
    write_audit(Path(args.audit_output), warnings)

    if warnings:
        print(f"[audit] Completed with {len(warnings)} warning(s).")
        return 1

    print("[audit] Completed with no warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
