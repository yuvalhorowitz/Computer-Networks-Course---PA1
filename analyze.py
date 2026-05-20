#!/usr/bin/env python3
"""
analyze.py

Reads the server/client TSV outputs produced by run_experiments.sh and
computes the statistics + charts required by the assignment README:

    * Average and median job system time  (departure - arrival)
    * Average and median queue occupancy   (q_num column)
    * Drop count + % (bounded experiments only)
    * Queue size over time chart           charts/<exp>_qsize.png
    * Job system time histogram (10 bins)  charts/<exp>_hist.png
    * Combined multi-page report           charts/all_experiments.pdf
    * Summary table                        summary.csv

Usage:
    python3 analyze.py [results_dir]

Defaults to ./results.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


# Server TSV columns:
#   addr  id:idx  arrival_ns  departure_ns  q_num  q_time
SERVER_COLS = ["addr", "id_idx", "arrival_ns", "departure_ns", "q_num", "q_time"]

# Client TSV columns:
#   addr  id:idx  floor_x  floor_y
CLIENT_COLS = ["addr", "id_idx", "floor_x", "floor_y"]


def parse_experiment_name(name: str) -> dict:
    """Extract (mu, lambda, num_jobs, q_size, two_clients) from the experiment name.

    Names look like:
        exp1_mu5_lam3_n1000          → mu=5,  lam=3,  n=1000, q=unbounded
        exp2_mu50_lam20_2x2000       → mu=50, lam=20, 2 clients × 2000
        exp3_mu50_lam48_q10          → mu=50, lam=48, n=2000, q=10
    """
    m = re.match(r"exp(\d+)_mu(\d+)_lam(\d+)(?:_n(\d+))?(?:_(\d+)x(\d+))?(?:_q(\d+))?$", name)
    if not m:
        return {"experiment_num": None, "mu": None, "lam": None,
                "num_jobs": None, "q_size": None, "two_clients": False}

    exp_num = int(m.group(1))
    mu = int(m.group(2))
    lam = int(m.group(3))
    n = int(m.group(4)) if m.group(4) else None
    n_clients = int(m.group(5)) if m.group(5) else 1
    n_per_client = int(m.group(6)) if m.group(6) else None
    q_size = int(m.group(7)) if m.group(7) else None

    if n_per_client is not None:
        num_jobs = n_clients * n_per_client
    else:
        num_jobs = n

    return {
        "experiment_num": exp_num,
        "mu": mu,
        "lam": lam,
        "num_jobs": num_jobs,
        "q_size": q_size,                # None means unbounded
        "two_clients": n_clients == 2,
    }


def discover_experiments(results_dir: Path) -> list[str]:
    """List unique experiment names by stripping `_server.tsv` from server files."""
    server_files = sorted(results_dir.glob("*_server.tsv"))
    return [f.name[:-len("_server.tsv")] for f in server_files]


def load_server(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", header=None, names=SERVER_COLS)
    df["system_time_us"] = (df["departure_ns"] - df["arrival_ns"]) / 1000.0
    return df


def count_client_sends(results_dir: Path, exp_name: str) -> int:
    """Sum of lines across all client TSVs for this experiment."""
    total = 0
    for pattern in (f"{exp_name}_client.tsv", f"{exp_name}_client_a.tsv", f"{exp_name}_client_b.tsv"):
        path = results_dir / pattern
        if path.exists():
            with path.open() as f:
                total += sum(1 for _ in f)
    return total


def compute_stats(server_df: pd.DataFrame, exp_name: str, results_dir: Path) -> dict:
    params = parse_experiment_name(exp_name)
    sent = count_client_sends(results_dir, exp_name)
    got = len(server_df)
    drops = sent - got
    rho = params["lam"] / params["mu"] if (params["mu"] and params["lam"]) else None

    return {
        "experiment": exp_name,
        "mu": params["mu"],
        "lambda": params["lam"],
        "rho": rho,
        "num_jobs": params["num_jobs"],
        "q_size": params["q_size"] if params["q_size"] is not None else "unbounded",
        "sent": sent,
        "processed": got,
        "drops": drops,
        "drop_pct": (drops / sent * 100.0) if sent else 0.0,
        "mean_system_time_us": server_df["system_time_us"].mean(),
        "median_system_time_us": server_df["system_time_us"].median(),
        "mean_q_num": server_df["q_num"].mean(),
        "median_q_num": server_df["q_num"].median(),
        "max_q_num": int(server_df["q_num"].max()),
    }


def plot_queue_size(server_df: pd.DataFrame, title: str, ax=None):
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(server_df.index, server_df["q_num"], linewidth=0.6)
    ax.set_xlabel("Job (sequence index)")
    ax.set_ylabel("q_num at completion")
    ax.set_title(f"{title} — queue size over time")
    ax.grid(True, alpha=0.3)


def plot_system_time_histogram(server_df: pd.DataFrame, title: str, ax=None):
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(server_df["system_time_us"], bins=10, edgecolor="black")
    ax.set_xlabel("System time (µs)")
    ax.set_ylabel("Count of jobs")
    ax.set_title(f"{title} — system-time histogram (10 bins)")
    ax.grid(True, alpha=0.3)


def main(argv: list[str]) -> int:
    results_dir = Path(argv[1]) if len(argv) > 1 else Path("results")
    if not results_dir.is_dir():
        print(f"error: {results_dir} is not a directory", file=sys.stderr)
        return 1

    charts_dir = Path("charts")
    charts_dir.mkdir(exist_ok=True)

    experiments = discover_experiments(results_dir)
    if not experiments:
        print(f"error: no *_server.tsv files found in {results_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(experiments)} experiments in {results_dir}/")
    print()

    all_stats: list[dict] = []
    pdf_path = charts_dir / "all_experiments.pdf"

    with PdfPages(pdf_path) as pdf:
        for exp_name in experiments:
            server_path = results_dir / f"{exp_name}_server.tsv"
            print(f"  [{exp_name}]")

            df = load_server(server_path)
            stats = compute_stats(df, exp_name, results_dir)
            all_stats.append(stats)

            # Individual PNGs
            fig, ax = plt.subplots(figsize=(9, 4))
            plot_queue_size(df, exp_name, ax=ax)
            fig.tight_layout()
            fig.savefig(charts_dir / f"{exp_name}_qsize.png", dpi=120)
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(9, 4))
            plot_system_time_histogram(df, exp_name, ax=ax)
            fig.tight_layout()
            fig.savefig(charts_dir / f"{exp_name}_hist.png", dpi=120)
            plt.close(fig)

            # Combined PDF page (both charts side-by-side + stats annotation)
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))
            plot_queue_size(df, exp_name, ax=axes[0])
            plot_system_time_histogram(df, exp_name, ax=axes[1])
            stats_text = (
                f"μ={stats['mu']}   λ={stats['lambda']}   ρ={stats['rho']:.2f}\n"
                f"sent={stats['sent']}  processed={stats['processed']}  "
                f"drops={stats['drops']} ({stats['drop_pct']:.2f}%)\n"
                f"system time:  mean={stats['mean_system_time_us']:.1f}µs  "
                f"median={stats['median_system_time_us']:.1f}µs\n"
                f"q_num:  mean={stats['mean_q_num']:.2f}  "
                f"median={stats['median_q_num']:.1f}  max={stats['max_q_num']}"
            )
            fig.suptitle(exp_name, fontsize=12, y=1.02)
            fig.text(0.5, -0.05, stats_text, ha="center", va="top",
                     fontsize=9, family="monospace")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    # Summary CSV
    summary_df = pd.DataFrame(all_stats)
    summary_df.to_csv("summary.csv", index=False, float_format="%.3f")

    # Pretty terminal summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    cols_to_show = ["experiment", "rho", "sent", "processed", "drops", "drop_pct",
                    "mean_system_time_us", "median_system_time_us",
                    "mean_q_num", "median_q_num", "max_q_num"]
    with pd.option_context("display.max_rows", None,
                           "display.max_columns", None,
                           "display.width", 200,
                           "display.float_format", "{:.2f}".format):
        print(summary_df[cols_to_show].to_string(index=False))

    print()
    print(f"Charts (individual PNGs): {charts_dir}/<exp>_qsize.png and _hist.png")
    print(f"Combined PDF:            {pdf_path}")
    print(f"Summary CSV:             summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
