#!/usr/bin/env python3
"""
ORBIT Energy Post-Processor
Aligns WaveForms scope CSV with ORBIT benchmark CSV to fill in energy columns.

Usage:
    python3 tools/process_energy.py \
        --scope <waveforms_export.csv> \
        --orbit <pico_ascon_aead128.csv> \
        --shunt 0.1 \
        --vdd 3.3 \
        --rate 32000 \
        --runs 1-5 \
        --output <output.csv>

WaveForms Record-to-File CSV format used by ORBIT (2 columns, no header):
    channel_1_V, digital_bitfield

Older differential exports with three columns are also supported:
    channel_1_V, channel_2_V, digital_bitfield

Digital bitfield:
    bit 0 = DIO0 / GP15 measurement window
    bit 1 = DIO1 / GP14 whole-benchmark frame

ORBIT CSV format:
    run, timestamp_iso, ..., enc_time_us_total, dec_time_us_total, ...
    energy columns are 0.0 and will be filled in.

For automated ORBIT multi-run captures, record one long WaveForms file and use
--runs 1-5. The script maps GP14/DIO1 frame 1 to run 1, frame 2 to run 2, etc.
"""

import argparse
import csv
import re
import sys
import numpy as np

ORBIT_FIELDNAMES = [
    "run",
    "timestamp_iso",
    "run_id",
    "algorithm",
    "implementation",
    "version",
    "board",
    "arch",
    "compiler",
    "compiler_version",
    "cflags",
    "freq_hz",
    "msg_len",
    "ad_len",
    "key_len",
    "nonce_len",
    "tag_len",
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
    "ok",
    "notes",
]

ENERGY_FIELDNAMES = [
    "energy_uJ_enc_total",
    "energy_uJ_dec_total",
    "energy_uJ_per_byte_enc",
    "energy_uJ_per_byte_dec",
    "avg_power_mW_enc",
    "avg_power_mW_dec",
]


def log(msg):
    print(f"[energy] {msg}")


def parse_run_list(run_expr):
    """Parse run expressions like '1', '1,3,5', or '1-5'."""
    runs = []
    for part in run_expr.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            step = 1 if end >= start else -1
            runs.extend(range(start, end + step, step))
        else:
            runs.append(int(part))

    if not runs:
        raise ValueError("No runs were specified")
    return runs


def scope_path_for_run(scope_arg, run, auto_number=False):
    """
    Resolve the scope file for a run.

    Preferred explicit form:
        pico_ascon_run{run}.csv

    Convenience form:
        pico_ascon_run1.csv with --runs 1-5 becomes
        pico_ascon_run1.csv, pico_ascon_run2.csv, ...
    """
    if run is None:
        return scope_arg

    if "{run}" in scope_arg:
        return scope_arg.format(run=run)

    if not auto_number:
        return scope_arg

    match = list(re.finditer(r"\d+", scope_arg))
    if not match:
        raise ValueError("Use {run} in --scope or include a run number in the scope filename when using --runs")

    last = match[-1]
    width = last.end() - last.start()
    run_text = str(run).zfill(width) if width > 1 else str(run)
    return f"{scope_arg[:last.start()]}{run_text}{scope_arg[last.end():]}"


def resolve_digital_col(num_cols, requested_col):
    """Resolve requested 1-based digital column. 0 means auto-detect."""
    if requested_col == 0:
        return num_cols - 1

    digital_col = requested_col - 1
    if digital_col < 0:
        raise ValueError("--digital-column must be 0 for auto-detect or a positive 1-based column index")
    if digital_col >= num_cols:
        raise ValueError(f"Scope CSV has {num_cols} columns, but digital column {requested_col} was requested")
    return digital_col


def load_scope_csv(path, sample_rate_hz, voltage_mode, digital_column):
    """Load WaveForms export CSV. Returns numpy arrays: time, shunt voltage, digital bitfield."""
    log(f"Loading scope CSV: {path}")
    data = np.loadtxt(path, delimiter=",")
    if data.ndim == 1:
        raise ValueError("Scope CSV has only one row — check export settings")
    if data.shape[1] < 2:
        raise ValueError("Scope CSV must contain at least one analog column and one digital bitfield column")

    time_s = np.arange(data.shape[0], dtype=float) / sample_rate_hz
    ch1 = data[:, 0]
    digital_col = resolve_digital_col(data.shape[1], digital_column)
    ch2 = data[:, 1] if data.shape[1] >= 3 and digital_col != 1 else None

    if voltage_mode == "ch1":
        voltage = ch1
    elif voltage_mode == "ch2":
        if ch2 is None:
            raise ValueError("--voltage-mode ch2 requires at least 2 analog columns")
        voltage = ch2
    elif voltage_mode == "diff":
        if ch2 is None:
            raise ValueError("--voltage-mode diff requires CH1 and CH2")
        voltage = ch1 - ch2
    elif voltage_mode == "diff-reverse":
        if ch2 is None:
            raise ValueError("--voltage-mode diff-reverse requires CH1 and CH2")
        voltage = ch2 - ch1
    else:
        raise ValueError(f"Unknown voltage mode: {voltage_mode}")

    digital = data[:, digital_col].astype(int)

    log(f"  Loaded {len(time_s):,} samples")
    log(f"  Duration: {time_s[-1] - time_s[0]:.3f} s")
    log(f"  Sample rate: {sample_rate_hz:.0f} Hz")
    log(f"  Voltage mode: {voltage_mode}")
    log(f"  Digital column: {digital_col + 1}")
    log(f"  Shunt voltage range: {voltage.min()*1000:.3f} mV to {voltage.max()*1000:.3f} mV")
    log(f"  Digital states: {', '.join(str(v) for v in sorted(set(digital.tolist())))}")

    if digital.any():
        log(f"  Digital transitions detected: {np.sum(np.diff(digital) != 0)}")
    else:
        log("  Digital column is all zeros — will use voltage threshold for window detection")

    return time_s, voltage, digital


def _find_high_windows(mask):
    """Return (start_idx, end_idx) windows for contiguous True regions."""
    state = mask.astype(np.int8)
    edges = np.diff(state)
    rising = (np.where(edges > 0)[0] + 1).tolist()
    falling = (np.where(edges < 0)[0] + 1).tolist()

    if len(state) and state[0]:
        rising.insert(0, 0)
    if len(state) and state[-1]:
        falling.append(len(state))

    windows = []
    fall_idx = 0
    for r in rising:
        while fall_idx < len(falling) and falling[fall_idx] <= r:
            fall_idx += 1
        if fall_idx >= len(falling):
            break
        windows.append((r, falling[fall_idx]))
        fall_idx += 1
    return windows


def find_frame_windows(digital, frame_bit=1):
    if not digital.any():
        return []
    frame_mask = (digital & (1 << frame_bit)) != 0
    return _find_high_windows(frame_mask)


def find_trigger_windows(time_s, digital, voltage, measurement_bit=0, frame_bit=1, frame_window=None, v_threshold_mv=5.0):
    """
    Find measurement windows using DIO0/GP15 high periods.
    Falls back to voltage threshold if digital is not available.
    Returns list of (start_idx, end_idx) tuples.
    """
    if digital.any():
        measurement_mask = (digital & (1 << measurement_bit)) != 0
        frame_mask = (digital & (1 << frame_bit)) != 0

        windows = _find_high_windows(measurement_mask)
        frames = _find_high_windows(frame_mask)

        log(f"  Using DIO{measurement_bit} bit for measurement windows")
        log(f"  Found {len(frames)} frame window(s) on DIO{frame_bit}")

        if frame_window:
            frame_start, frame_end = frame_window
            windows = [(s, e) for s, e in windows if s >= frame_start and e <= frame_end]
        elif frames:
            frame_start, frame_end = frames[0]
            windows = [(s, e) for s, e in windows if s >= frame_start and e <= frame_end]
    else:
        log(f"  Using voltage threshold ({v_threshold_mv} mV) for window detection")
        threshold_v = v_threshold_mv / 1000.0
        windows = []
        for r, f in _find_high_windows(np.abs(voltage) > threshold_v):
            # Filter out very short glitches (< 1ms)
            duration = time_s[f] - time_s[r]
            if duration > 0.001:
                windows.append((r, f))

    log(f"  Found {len(windows)} trigger windows")
    return windows


def compute_energy(time_s, voltage, start_idx, end_idx, shunt_ohm, vdd_v):
    """
    Compute energy in microjoules for a window.
    E = integral(V_shunt / R_shunt * V_dd * dt)
    """
    t = time_s[start_idx:end_idx]
    v = voltage[start_idx:end_idx]

    if len(t) < 2:
        return 0.0, 0.0, 0.0

    # Lead orientation determines sign. Energy use is a magnitude, so integrate
    # absolute shunt voltage after selecting the requested voltage mode.
    current_a = np.abs(v) / shunt_ohm  # I = |V|/R
    power_w   = current_a * vdd_v      # P = I * V_dd
    dt        = np.diff(t)
    energy_j  = np.trapezoid(power_w, t)
    energy_uj = energy_j * 1e6

    duration_s    = t[-1] - t[0]
    avg_power_mw  = (energy_j / duration_s * 1000) if duration_s > 0 else 0.0

    return energy_uj, avg_power_mw, duration_s


def row_is_kem(row):
    return row.get("algorithm") == "ml_kem_512" or row.get("notes") in {"keygen", "encap", "decap"}


def load_orbit_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        raw_rows = list(csv.reader(f))

    if not raw_rows:
        raise ValueError("ORBIT CSV is empty")

    header = raw_rows[0]
    use_canonical = header != ORBIT_FIELDNAMES
    if use_canonical:
        log("  ORBIT CSV header did not match expected schema; using canonical ORBIT fieldnames")

    rows = []
    for line_no, raw in enumerate(raw_rows[1:], start=2):
        if len(raw) < len(ORBIT_FIELDNAMES):
            log(f"  WARNING: skipping short ORBIT CSV row {line_no} with {len(raw)} field(s)")
            continue
        if len(raw) > len(ORBIT_FIELDNAMES):
            log(f"  WARNING: trimming ORBIT CSV row {line_no} from {len(raw)} to {len(ORBIT_FIELDNAMES)} fields")
            raw = raw[:len(ORBIT_FIELDNAMES)]
        rows.append(dict(zip(ORBIT_FIELDNAMES, raw)))

    return ORBIT_FIELDNAMES, dedupe_kem_rows(rows)


def dedupe_kem_rows(rows):
    if not any(row.get("algorithm") == "ml_kem_512" or row.get("notes") in {"keygen", "encap", "decap"} for row in rows):
        return rows

    grouped = {}
    order = []
    for row in rows:
        run = row.get("run", "")
        note = row.get("notes", "")
        if row.get("algorithm") == "ml_kem_512" or note in {"keygen", "encap", "decap"}:
            key = (run, note)
            if key not in grouped:
                order.append(key)
            grouped[key] = row
        else:
            key = ("__row__", str(len(order)))
            order.append(key)
            grouped[key] = row

    kem_order = {"keygen": 0, "encap": 1, "decap": 2}
    runs = sorted(
        {run for run, note in grouped if run != "__row__" and note in kem_order},
        key=lambda value: int(value) if str(value).isdigit() else str(value),
    )
    non_kem = [grouped[key] for key in order if key[0] == "__row__"]
    compact = list(non_kem)
    removed = 0

    for run in runs:
        for note in sorted(kem_order, key=kem_order.get):
            row = grouped.get((run, note))
            if row is not None:
                compact.append(row)

    if len(compact) != len(rows):
        removed = len(rows) - len(compact)
        log(f"  Collapsed duplicate ML-KEM operation rows; removed {removed} duplicate row(s)")

    return compact


def assign_windows_to_rows(orbit_rows, windows, time_s, voltage, shunt_ohm, vdd_v, run=None):
    """
    AEAD rows have enc and dec measurement windows (2 windows per row).
    ML-KEM rows have one operation window per row, stored in the enc fields.
    With --run, only rows whose run column matches that value are updated.
    """
    if run is None:
        target_indices = list(range(len(orbit_rows)))
        run_label = "all runs"
    else:
        target_indices = [
            i for i, row in enumerate(orbit_rows)
            if str(row.get("run", "")).strip() == str(run)
        ]
        run_label = f"run {run}"

    num_rows = len(target_indices)
    expected_windows = sum(1 if row_is_kem(orbit_rows[i]) else 2 for i in target_indices)

    log(f"  Target rows ({run_label}): {num_rows}, expected windows: {expected_windows}, found: {len(windows)}")

    if run is not None and not target_indices:
        raise ValueError(f"No rows found for run {run}")

    if len(windows) < expected_windows:
        log(f"  WARNING: fewer windows than expected — got {len(windows)}, need {expected_windows}")
        log("  This may happen if the record started after the benchmark began.")
        log("  Will assign available windows sequentially.")
    elif len(windows) > expected_windows:
        log(f"  WARNING: more windows than expected — got {len(windows)}, need {expected_windows}")
        log("  Extra windows will be ignored.")

    results = [dict(row) for row in orbit_rows]
    win_idx = 0

    for row_count, row_idx in enumerate(target_indices, start=1):
        row = orbit_rows[row_idx]
        is_kem = row_is_kem(row)
        enc_uj = dec_uj = 0.0
        enc_mw = dec_mw = 0.0
        enc_dur = dec_dur = 0.0

        # AEAD encryption window, or ML-KEM operation window.
        if win_idx < len(windows):
            s, e = windows[win_idx]
            enc_uj, enc_mw, enc_dur = compute_energy(
                time_s, voltage, s, e, shunt_ohm, vdd_v)
            win_idx += 1

        # AEAD decryption window. ML-KEM has one row/window per operation.
        if not is_kem and win_idx < len(windows):
            s, e = windows[win_idx]
            dec_uj, dec_mw, dec_dur = compute_energy(
                time_s, voltage, s, e, shunt_ohm, vdd_v)
            win_idx += 1

        msg_len = int(row.get("msg_len", 0) or 0)
        iterations = int(row.get("iterations", 1))

        enc_uj_per_byte = enc_uj / (msg_len * iterations) if msg_len > 0 and not is_kem else 0.0
        dec_uj_per_byte = dec_uj / (msg_len * iterations) if msg_len > 0 and not is_kem else 0.0

        if is_kem:
            op_name = row.get("notes", "op")
            log(f"  CSV row {row_idx + 2} ({run_label}, item {row_count}) {op_name}: "
                f"op={enc_uj:.2f} uJ ({enc_dur*1000:.1f}ms)")
        else:
            log(f"  CSV row {row_idx + 2} ({run_label}, item {row_count}) msg_len={msg_len}: "
                f"enc={enc_uj:.2f} uJ ({enc_dur*1000:.1f}ms), "
                f"dec={dec_uj:.2f} uJ ({dec_dur*1000:.1f}ms)")

        result = results[row_idx]
        result["energy_uJ_enc_total"]    = f"{enc_uj:.6f}"
        result["energy_uJ_dec_total"]    = f"{dec_uj:.6f}"
        result["energy_uJ_per_byte_enc"] = f"{enc_uj_per_byte:.6f}"
        result["energy_uJ_per_byte_dec"] = f"{dec_uj_per_byte:.6f}"
        result["avg_power_mW_enc"]       = f"{enc_mw:.6f}"
        result["avg_power_mW_dec"]       = f"{dec_mw:.6f}"
        if str(result.get("ok", "")).strip() == "":
            result["ok"] = "1"

    return results


def expected_windows_for_run(orbit_rows, run):
    target_rows = [
        row for row in orbit_rows
        if str(row.get("run", "")).strip() == str(run)
    ]
    return sum(1 if row_is_kem(row) else 2 for row in target_rows)


def process_scope_for_run(results, run, scope_path, args):
    log(f"Processing {'run ' + str(run) if run is not None else 'all runs'} from: {scope_path}")

    time_s, voltage, digital = load_scope_csv(
        scope_path,
        sample_rate_hz=args.rate,
        voltage_mode=args.voltage_mode,
        digital_column=args.digital_column,
    )

    log("Finding measurement windows...")
    windows = find_trigger_windows(
        time_s,
        digital,
        voltage,
        measurement_bit=args.measurement_bit,
        frame_bit=args.frame_bit,
        v_threshold_mv=args.threshold,
    )

    if not windows:
        log("ERROR: No trigger windows found.")
        log("  Check that DIO0/GP15 is connected and the benchmark ran during recording.")
        sys.exit(1)

    log("Assigning energy windows to benchmark rows...")
    return assign_windows_to_rows(
        results, windows, time_s, voltage, args.shunt, args.vdd, run=run)


def process_single_scope_multi_run(results, run_targets, scope_path, args):
    log(f"Processing runs {run_targets[0]}-{run_targets[-1]} from one scope file: {scope_path}")

    time_s, voltage, digital = load_scope_csv(
        scope_path,
        sample_rate_hz=args.rate,
        voltage_mode=args.voltage_mode,
        digital_column=args.digital_column,
    )

    frames = find_frame_windows(digital, frame_bit=args.frame_bit)
    log(f"  Multi-run mode: found {len(frames)} frame window(s) on DIO{args.frame_bit}")

    candidate_frames = []
    min_expected_windows = min(
        expected_windows_for_run(results, run)
        for run in run_targets
    )

    for frame_idx, frame in enumerate(frames, start=1):
        frame_windows = find_trigger_windows(
            time_s,
            digital,
            voltage,
            measurement_bit=args.measurement_bit,
            frame_bit=args.frame_bit,
            frame_window=frame,
            v_threshold_mv=args.threshold,
        )
        if len(frame_windows) >= min_expected_windows:
            candidate_frames.append((frame, frame_windows))
        elif frame_windows:
            start, end = frame
            log(
                f"  Ignoring frame {frame_idx} at {time_s[start]:.3f}s-{time_s[end - 1]:.3f}s "
                f"with only {len(frame_windows)} measurement window(s); expected at least {min_expected_windows}"
            )
        else:
            start, end = frame
            log(f"  Ignoring frame {frame_idx} at {time_s[start]:.3f}s-{time_s[end - 1]:.3f}s with no measurement windows")

    if len(candidate_frames) < len(run_targets):
        raise ValueError(
            f"Found {len(candidate_frames)} frame(s) containing measurement windows, "
            f"but {len(run_targets)} run(s) were requested"
        )
    if len(candidate_frames) == (2 * len(run_targets)):
        log("  Detected two usable frames per requested run; using every second frame after reset")
        candidate_frames = candidate_frames[1::2]
    if len(candidate_frames) > len(run_targets):
        log(f"  WARNING: found {len(candidate_frames)} usable frame(s), but only {len(run_targets)} run(s) were requested")
        log("  Extra usable frames will be ignored.")

    for run, (frame, windows) in zip(run_targets, candidate_frames):
        start, end = frame
        log(f"Finding measurement windows for run {run} inside frame {time_s[start]:.3f}s-{time_s[end - 1]:.3f}s...")

        log("Assigning energy windows to benchmark rows...")
        results = assign_windows_to_rows(
            results, windows, time_s, voltage, args.shunt, args.vdd, run=run)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="ORBIT energy post-processor — aligns WaveForms scope data with ORBIT CSV"
    )
    parser.add_argument("--scope",  required=True, help="WaveForms Record-to-File export CSV")
    parser.add_argument("--orbit",  required=True, help="ORBIT benchmark CSV")
    parser.add_argument("--shunt",  type=float, default=0.1,  help="Shunt resistance in ohms (default: 0.1)")
    parser.add_argument("--vdd",    type=float, default=3.3,   help="Supply voltage in volts (default: 3.3)")
    parser.add_argument("--rate",   type=float, required=True, help="WaveForms sample rate in Hz, e.g. 32000")
    parser.add_argument("--run",    type=int, default=None,
                        help="Only update ORBIT rows for this run index, e.g. --run 1")
    parser.add_argument("--runs",   default=None,
                        help="Update multiple runs from sequential scope files, e.g. --runs 1-5 or --runs 1,3,5")
    parser.add_argument("--multi-run-scope", action="store_true",
                        help="Treat --scope as one long WaveForms file with one GP14/DIO1 frame per requested run")
    parser.add_argument("--output", default=None, help="Output CSV path (default: overwrites orbit CSV)")
    parser.add_argument("--voltage-mode", choices=("ch1", "ch2", "diff", "diff-reverse"), default="ch1",
                        help="How to compute shunt voltage from analog columns (default: ch1)")
    parser.add_argument("--digital-column", type=int, default=0,
                        help="1-based WaveForms digital bitfield column, or 0 to auto-detect the last column (default: 0)")
    parser.add_argument("--measurement-bit", type=int, default=0,
                        help="Digital bit for GP15/DIO0 measurement windows (default: 0)")
    parser.add_argument("--frame-bit", type=int, default=1,
                        help="Digital bit for GP14/DIO1 frame window (default: 1)")
    parser.add_argument("--threshold", type=float, default=2.0,
                        help="Voltage threshold in mV for window detection when DIO0 not available (default: 2.0)")
    args = parser.parse_args()

    if args.run is not None and args.runs is not None:
        raise ValueError("Use either --run or --runs, not both")

    run_targets = parse_run_list(args.runs) if args.runs else [args.run]

    # Load ORBIT CSV
    log(f"Loading ORBIT CSV: {args.orbit}")
    fieldnames, orbit_rows = load_orbit_csv(args.orbit)
    log(f"  Loaded {len(orbit_rows)} benchmark rows")

    results = [dict(row) for row in orbit_rows]

    if args.multi_run_scope:
        if args.runs is None:
            raise ValueError("--multi-run-scope requires --runs")
        results = process_single_scope_multi_run(results, run_targets, args.scope, args)
    else:
        for run in run_targets:
            scope_path = scope_path_for_run(args.scope, run, auto_number=args.runs is not None)
            results = process_scope_for_run(results, run, scope_path, args)

    # Write output
    output_path = args.output or args.orbit
    for field in ENERGY_FIELDNAMES:
        if field not in fieldnames:
            fieldnames.append(field)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    log(f"Written to: {output_path}")
    log("Done.")


if __name__ == "__main__":
    main()
