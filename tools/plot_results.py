"""
ORBIT Benchmark Plotter
Generates publication-quality charts from ORBIT CSV result files.
 
Usage:
    python3 tools/plot_results.py --results_dir results/ --board pico
    python3 tools/plot_results.py --results_dir results/ --board pico --output_dir plots/
    python3 tools/plot_results.py --summary_files results/summary/stm32_summary.csv results/summary/esp32c61_summary.csv --compare
"""

import argparse
import os
import glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MPLCONFIGDIR", os.path.join(PROJECT_ROOT, ".matplotlib"))

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

ALGORITHM_COLORS = {
    "ascon_aead128":  "#185FA5",
    "ascon_aead80pq": "#0F6E56",
    "gift_cofb":      "#993C1D",
    "aes_128_gcm":    "#888780",
    "ml_kem_512":     "#534AB7",
}

ALGORITHM_LABELS = {
    "ascon_aead128":  "Ascon-128",
    "ascon_aead80pq": "Ascon-80pq",
    "gift_cofb":      "GIFT-COFB",
    "aes_128_gcm":    "AES-128-GCM",
    "ml_kem_512":     "ML-KEM-512",
}

AEAD_ALGORITHMS = [k for k in ALGORITHM_LABELS if k != "ml_kem_512"]
MSG_SIZES = [16, 64, 256, 1024, 4096, 16384]
MSG_LABELS = ["16B", "64B", "256B", "1KB", "4KB", "16KB"]
BOARD_LABELS = {
    "esp32c61": "ESP32-C61",
    "stm32": "STM32 F446RE",
    "pico": "RP2040 Pico",
    "nrf52": "nRF52832",
    "rpi5": "Raspberry Pi 5",
}

COMPARISON_METRICS = {
    "cycles_per_byte": ("enc_cycles_per_byte_mean", "Cycles/Byte"),
    "latency": ("enc_time_us_per_op_mean", "Latency (us/op)"),
    "energy_per_byte": ("energy_uJ_per_byte_enc_mean", "Energy (uJ/byte)"),
    "energy_per_op": ("energy_uJ_per_op_enc_mean", "Energy (uJ/op)"),
    "avg_power": ("avg_power_mW_enc_mean", "Average Power (mW)"),
}

def load_results(results_dir, board=None):
    files = glob.glob(os.path.join(results_dir, "*.csv"))
    dfs = []
    for file in files:
        try:
            dfs.append(pd.read_csv(file))
        except Exception as e:
            print(f"Warning: Could not read {file}: {e}")
    if not dfs:
        raise ValueError(f"No valid CSV files found in {results_dir}")
        return pd.DataFrame() 
    df = pd.concat(dfs, ignore_index=True)
    return df[df["board"] == board] if board else df

def load_summary_files(paths):
    dfs = []
    for path in paths:
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f"Warning: Could not read {path}: {e}")
            continue
        df["source_file"] = path
        dfs.append(df)
    if not dfs:
        raise ValueError("No valid summary CSV files were loaded")
    return pd.concat(dfs, ignore_index=True)

def apply_style():
    plt.rcParams.update({
        "font.family":        "sans-serif",
        "font.size":          11,
        "axes.titlesize":     13,
        "axes.titleweight":   "normal",
        "axes.labelsize":     11,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.grid":          True,
        "grid.alpha":         0.3,
        "grid.linestyle":     "--",
        "legend.frameon":     False,
        "legend.fontsize":    10,
        "figure.dpi":         150,
        "savefig.dpi":        300,
        "savefig.bbox":       "tight",
    })

def us_formatter(x, _):
    return f"{x/1000:.1f}" if x >= 1000 else f"{int(x)}us"

def cbp_formatter(x, _):
    return f"{int(x/1000)}K" if x >= 1000 else str(int(x))

def save_figure(fig, output_path, filename):
    path = os.path.join(output_path, filename)
    fig.savefig(path)
    plt.close(fig)
    print(f"Saved: {path}")

def board_label(board):
    return BOARD_LABELS.get(str(board), str(board))

def mean_for(df, algo, col, msg_len=None, note=None):
    mask = df["algorithm"] == algo
    if msg_len is not None:
        mask &= df["msg_len"] == msg_len
    if note is not None:
        mask &= df["notes"] == note
    subset = df[mask]
    return subset[col].mean() if not subset.empty else None

def summary_value(df, board, algo, col, msg_len=None, note=None):
    mask = (df["board"] == board) & (df["algorithm"] == algo)
    if msg_len is not None:
        mask &= df["msg_len"] == msg_len
    if note is not None:
        mask &= df["notes"] == note
    subset = df[mask]
    if subset.empty or col not in subset:
        return None
    value = subset[col].iloc[0]
    return None if pd.isna(value) else value

def plot_summary_aead_lines(df, output_dir, metric_key, operation_label="Encryption"):
    col, ylabel = COMPARISON_METRICS[metric_key]
    if col not in df.columns:
        print(f"Skipping {metric_key}: column {col} not found")
        return

    boards = sorted(df["board"].dropna().unique().tolist())
    for algo in AEAD_ALGORITHMS:
        fig, ax = plt.subplots(figsize=(8, 5))
        plotted = False
        for board in boards:
            points = [summary_value(df, board, algo, col, msg_len=m) for m in MSG_SIZES]
            if all(v is None or v == 0 for v in points):
                continue
            ax.plot(
                range(len(MSG_SIZES)),
                points,
                label=board_label(board),
                linewidth=2,
                marker="o",
                markersize=5,
            )
            plotted = True
        if not plotted:
            plt.close(fig)
            continue

        ax.set_xticks(range(len(MSG_SIZES)))
        ax.set_xticklabels(MSG_LABELS)
        ax.set_xlabel("Message Size")
        ax.set_ylabel(ylabel)
        if metric_key in {"cycles_per_byte", "latency", "energy_per_byte", "energy_per_op"}:
            ax.set_yscale("log")
        ax.set_title(f"{ALGORITHM_LABELS[algo]} {operation_label} Comparison")
        ax.legend(title="Platform")
        plt.tight_layout()
        save_figure(fig, output_dir, f"compare_{algo}_{metric_key}.png")

def plot_summary_metric_grid(df, output_dir, metric_key, msg_len=1024):
    col, ylabel = COMPARISON_METRICS[metric_key]
    if col not in df.columns:
        print(f"Skipping {metric_key}: column {col} not found")
        return

    boards = sorted(df["board"].dropna().unique().tolist())
    labels = [ALGORITHM_LABELS[a] for a in AEAD_ALGORITHMS]
    x = range(len(labels))
    width = 0.8 / max(len(boards), 1)

    fig, ax = plt.subplots(figsize=(9, 5))
    for idx, board in enumerate(boards):
        values = [
            summary_value(df, board, algo, col, msg_len=msg_len) or 0
            for algo in AEAD_ALGORITHMS
        ]
        offsets = [i - 0.4 + width / 2 + idx * width for i in x]
        ax.bar(offsets, values, width=width, label=board_label(board), zorder=3)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel(ylabel)
    if metric_key in {"cycles_per_byte", "latency", "energy_per_byte", "energy_per_op"}:
        ax.set_yscale("log")
    msg_label = MSG_LABELS[MSG_SIZES.index(msg_len)] if msg_len in MSG_SIZES else f"{msg_len}B"
    ax.set_title(f"AEAD {ylabel} at {msg_label}")
    ax.legend(title="Platform")
    plt.tight_layout()
    save_figure(fig, output_dir, f"compare_aead_{metric_key}_{msg_len}.png")

def plot_summary_mlkem(df, output_dir, metric_key="latency"):
    col = "enc_time_us_per_op_mean" if metric_key == "latency" else "energy_uJ_per_op_enc_mean"
    ylabel = "Latency (us/op)" if metric_key == "latency" else "Energy (uJ/op)"
    if col not in df.columns:
        print(f"Skipping ML-KEM {metric_key}: column {col} not found")
        return

    ops = [("keygen", "KeyGen"), ("encap", "Encapsulate"), ("decap", "Decapsulate")]
    boards = sorted(df["board"].dropna().unique().tolist())
    x = range(len(ops))
    width = 0.8 / max(len(boards), 1)

    fig, ax = plt.subplots(figsize=(8, 5))
    for idx, board in enumerate(boards):
        values = [
            summary_value(df, board, "ml_kem_512", col, msg_len=0, note=op) or 0
            for op, _ in ops
        ]
        offsets = [i - 0.4 + width / 2 + idx * width for i in x]
        ax.bar(offsets, values, width=width, label=board_label(board), zorder=3)

    ax.set_xticks(list(x))
    ax.set_xticklabels([label for _, label in ops])
    ax.set_ylabel(ylabel)
    ax.set_yscale("log")
    ax.set_title(f"ML-KEM-512 {ylabel} Comparison")
    ax.legend(title="Platform")
    plt.tight_layout()
    save_figure(fig, output_dir, f"compare_mlkem_{metric_key}.png")

def print_comparison_summary(df):
    print(f"\n{'='*72}")
    print("ORBIT platform comparison")
    print(f"{'='*72}")
    boards = sorted(df["board"].dropna().unique().tolist())
    print("Boards:", ", ".join(board_label(b) for b in boards))
    print("\nAEAD encryption cycles/byte at 1KB")
    print(f"{'Algorithm':<18}" + "".join(f"{board_label(b):>16}" for b in boards))
    print("-" * (18 + 16 * len(boards)))
    for algo in AEAD_ALGORITHMS:
        row = [summary_value(df, b, algo, "enc_cycles_per_byte_mean", msg_len=1024) for b in boards]
        print(f"{ALGORITHM_LABELS[algo]:<18}" + "".join(f"{v:>16,.1f}" if v else f"{'--':>16}" for v in row))

    print("\nML-KEM latency, ms/op")
    print(f"{'Operation':<18}" + "".join(f"{board_label(b):>16}" for b in boards))
    print("-" * (18 + 16 * len(boards)))
    for op, label in [("keygen", "KeyGen"), ("encap", "Encap"), ("decap", "Decap")]:
        row = [summary_value(df, b, "ml_kem_512", "enc_time_us_per_op_mean", msg_len=0, note=op) for b in boards]
        print(f"{label:<18}" + "".join(f"{v/1000:>16,.2f}" if v else f"{'--':>16}" for v in row))
    print(f"{'='*72}\n")

def plot_cycles_per_byte(df, output_path, board):
    fig, ax = plt.subplots(figsize=(8, 5))

    for algo in AEAD_ALGORITHMS:
        points = [mean_for(df, algo, "enc_cycles_per_byte", m) for m in MSG_SIZES]

        if all(v is None for v in points):
            continue
        ax.plot(
            range(len(MSG_SIZES)),
            points,
            label=ALGORITHM_LABELS[algo],
            color=ALGORITHM_COLORS[algo],
            linewidth=2,
            linestyle = "--" if algo == "aes_128_gcm" else "-",
            marker="o",
            markersize=5,
        )
    ax.set_yscale("log")
    ax.set_xticks(range(len(MSG_SIZES)))
    ax.set_xticklabels(MSG_LABELS)
    ax.set_xlabel("Message Size")
    ax.set_ylabel("Average Cycles/Byte (log scale)")
    ax.set_title(f"cycles per byte: AEAD algorithms\n{board} @ 125 MHz, -O2, reference implementations")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x/1000)}K" if x >= 1000 else f"{int(x)}"))
    ax.legend()
    plt.tight_layout()
    save_figure(fig, output_path, f"{board}_cycles_per_byte.png")

def plot_lwc_only(df, output_dir, board):
    fig, ax = plt.subplots(figsize=(8, 5))
    for algo in [a for a in AEAD_ALGORITHMS if a != "aes_128_gcm"]:
        points = [mean_for(df, algo, "enc_cycles_per_byte", m) for m in MSG_SIZES]
        if all(v is None for v in points):
            continue
        ax.plot(range(len(MSG_SIZES)), points,
                label=ALGORITHM_LABELS[algo], color=ALGORITHM_COLORS[algo],
                linewidth=2, marker="o", markersize=5)
    ax.set_xticks(range(len(MSG_SIZES)))
    ax.set_xticklabels(MSG_LABELS)
    ax.set_xlabel("message size")
    ax.set_ylabel("cycles per byte")
    ax.set_title(f"cycles per byte — LWC algorithms (linear scale)\n{board} @ 125 MHz, -O2")
    ax.legend()
    plt.tight_layout()
    save_figure(fig, output_dir, f"{board}_lwc_cycles_per_byte.png")


def plot_latency_comparison(df, output_dir, board):
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, msg_size in zip(axes, [16, 1024]):
        labels, values, colors = [], [], []
        for algo in AEAD_ALGORITHMS:
            v = mean_for(df, algo, "enc_time_us_per_op", msg_size)
            if v is not None:
                labels.append(ALGORITHM_LABELS[algo])
                values.append(v)
                colors.append(ALGORITHM_COLORS[algo])
        v = mean_for(df, "ml_kem_512", "enc_time_us_per_op", note="keygen")
        if v is not None:
            labels.append("ML-KEM-512\n(KeyGen)")
            values.append(v)
            colors.append(ALGORITHM_COLORS["ml_kem_512"])
        bars = ax.bar(range(len(labels)), values, color=colors,
                      width=0.6, edgecolor="none", zorder=3)
        ax.set_yscale("log")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9, rotation=15, ha="right")
        ax.set_ylabel("us per operation (log scale)")
        size_label = f"{msg_size}B" if msg_size < 1024 else f"{msg_size//1024}KB"
        ax.set_title(f"latency @ {size_label} payload")
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(us_formatter))
        for bar, val in zip(bars, values):
            label = f"{val/1000:.1f}ms" if val >= 1000 else f"{int(val)}us"
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() * 1.1, label,
                    ha="center", va="bottom", fontsize=8, color="#444")
    fig.suptitle(f"per-operation latency — {board} @ 125 MHz", y=1.02)
    plt.tight_layout()
    save_figure(fig, output_dir, f"{board}_latency_comparison.png")
 
 
def plot_mlkem_operations(df, output_dir, board):
    ops = [("keygen", "KeyGen"), ("encap", "Encapsulate"), ("decap", "Decapsulate")]
    values = [mean_for(df, "ml_kem_512", "enc_time_us_per_op", note=op) or 0
              for op, _ in ops]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar([lbl for _, lbl in ops], values,
                  color=ALGORITHM_COLORS["ml_kem_512"], width=0.5, edgecolor="none", zorder=3)
    ref = mean_for(df, "ascon_aead128", "enc_time_us_per_op", msg_len=64)
    if ref:
        ax.axhline(ref, color=ALGORITHM_COLORS["ascon_aead128"],
                   linestyle="--", linewidth=1.5,
                   label=f"Ascon-128 @ 64B ({ref:.0f}us)")
        ax.legend()
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 200,
                f"{val/1000:.1f}ms", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("us per operation")
    ax.set_title(f"ML-KEM-512 operation latency\n{board} @ 125 MHz, -O2")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(us_formatter))
    plt.tight_layout()
    save_figure(fig, output_dir, f"{board}_mlkem_operations.png")
 
 
def plot_80pq_overhead(df, output_dir, board):
    overheads = []
    for m in MSG_SIZES:
        base = mean_for(df, "ascon_aead128",  "enc_cycles_per_byte", m)
        pq   = mean_for(df, "ascon_aead80pq", "enc_cycles_per_byte", m)
        overheads.append(((pq - base) / base * 100) if base and pq else 0)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(MSG_LABELS, overheads, color=ALGORITHM_COLORS["ascon_aead80pq"],
           width=0.5, edgecolor="none", zorder=3)
    ax.set_xlabel("message size")
    ax.set_ylabel("overhead vs Ascon-128 (%)")
    ax.set_title(f"Ascon-80pq overhead over Ascon-128\n{board} @ 125 MHz")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    plt.tight_layout()
    save_figure(fig, output_dir, f"{board}_ascon80pq_overhead.png")
 
 
def print_summary(df, board):
    print(f"\n{'='*65}")
    print(f"ORBIT summary — {board}")
    print(f"{'='*65}")
    print(f"{'Algorithm':<20} {'16B':>8} {'256B':>8} {'1KB':>8} {'16KB':>8}  cpb")
    print(f"{'-'*55}")
    for algo in AEAD_ALGORITHMS:
        vals = [mean_for(df, algo, "enc_cycles_per_byte", m)
                for m in [16, 256, 1024, 16384]]
        row = "  ".join(f"{v:>8,.0f}" if v else f"{'--':>8}" for v in vals)
        print(f"{ALGORITHM_LABELS[algo]:<20} {row}")
    print(f"\n{'Algorithm':<20} {'KeyGen':>10} {'Encap':>10} {'Decap':>10}  ms")
    print(f"{'-'*55}")
    vals = [mean_for(df, "ml_kem_512", "enc_time_us_per_op", note=op)
            for op in ["keygen", "encap", "decap"]]
    row = "  ".join(f"{v/1000:>10.2f}" if v else f"{'--':>10}" for v in vals)
    print(f"{'ML-KEM-512':<20} {row}")
    print(f"{'='*65}\n")
 
 
def main():
    parser = argparse.ArgumentParser(description="ORBIT benchmark plotter")
    parser.add_argument("--results_dir", default="results")
    parser.add_argument("--output_dir",  default="plots")
    parser.add_argument("--board",       default="pico")
    parser.add_argument("--summary_files", nargs="+", default=None,
                        help="Summary CSV files from tools/summarize_results.py")
    parser.add_argument("--compare", action="store_true",
                        help="Generate platform comparison plots from --summary_files")
    parser.add_argument("--comparison_msg_len", type=int, default=1024,
                        help="Message length for grouped AEAD comparison bars")
    args = parser.parse_args()
 
    os.makedirs(args.output_dir, exist_ok=True)
    apply_style()
 
    if args.summary_files:
        df = load_summary_files(args.summary_files)
        if args.compare:
            print(f"Loaded {len(df)} summary rows from {len(args.summary_files)} file(s)")
            plot_summary_aead_lines(df, args.output_dir, "cycles_per_byte")
            plot_summary_aead_lines(df, args.output_dir, "energy_per_byte")
            plot_summary_metric_grid(df, args.output_dir, "cycles_per_byte", msg_len=args.comparison_msg_len)
            plot_summary_metric_grid(df, args.output_dir, "latency", msg_len=args.comparison_msg_len)
            plot_summary_metric_grid(df, args.output_dir, "energy_per_byte", msg_len=args.comparison_msg_len)
            plot_summary_mlkem(df, args.output_dir, "latency")
            plot_summary_mlkem(df, args.output_dir, "energy")
            print_comparison_summary(df)
            print(f"All comparison plots saved to {args.output_dir}/")
            return

    df = load_results(args.results_dir, board=args.board)
    if df.empty:
        print("No data loaded. Check your results directory and board name.")
        return
 
    print(f"Loaded {len(df)} rows -- algorithms: {df['algorithm'].unique().tolist()}")
 
    plot_cycles_per_byte(df, args.output_dir, args.board)
    plot_lwc_only(df, args.output_dir, args.board)
    plot_latency_comparison(df, args.output_dir, args.board)
    plot_mlkem_operations(df, args.output_dir, args.board)
    plot_80pq_overhead(df, args.output_dir, args.board)
    print_summary(df, args.board)
 
    print(f"All plots saved to {args.output_dir}/")
 
 
if __name__ == "__main__":
    main()
