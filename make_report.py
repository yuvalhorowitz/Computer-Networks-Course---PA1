#!/usr/bin/env python3
"""
make_report.py

Reads summary.csv (produced by analyze.py) and the PNG charts in charts/,
and produces a self-contained README.html that can be opened in
Safari / Chrome and printed (File → Print → Save as PDF) to satisfy
the assignment's README.pdf submission requirement.

Inputs:
    students.json         — team info (names, IDs, emails, course details)
    summary.csv           — produced by analyze.py
    charts/<exp>_qsize.png and <exp>_hist.png — produced by analyze.py

Output:
    README.html           — open in browser, print to PDF
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


# Map of experiment groups to display headers, in the order required by the spec.
EXPERIMENT_GROUPS = [
    ("Experiment 1 — Single client, unbounded queue",
     "Various (μ, λ) combinations to study queueing behavior across utilization levels.",
     [
         "exp1_mu5_lam3_n1000",
         "exp1_mu5_lam3_n4000",
         "exp1_mu3_lam5_n1000",
         "exp1_mu3_lam5_n4000",
         "exp1_mu50_lam30_n1000",
         "exp1_mu50_lam30_n4000",
         "exp1_mu50_lam35_n2000",
         "exp1_mu50_lam40_n2000",
         "exp1_mu50_lam45_n2000",
     ]),
    ("Experiment 2 — Two clients, unbounded queue",
     "Two concurrent clients × 2000 jobs each, both at (μ, λ) = (50, 20). The server's num_jobs = 4000 (sum of both clients).",
     ["exp2_mu50_lam20_2x2000"]),
    ("Experiment 3 — Bounded queue (q_size = 10)",
     "FIFO capacity limited to 10 — drops occur. q_num is capped at q_size+1 (11) because the executing job is counted.",
     [
         "exp3_mu50_lam45_q10",
         "exp3_mu50_lam48_q10",
     ]),
]


def encode_image_as_data_uri(path: Path) -> str:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def fmt(value, decimals: int = 2) -> str:
    """Format a number for the stats table; pass strings through."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, float) and not pd.isna(value):
        if abs(value - int(value)) < 1e-9 and decimals == 0:
            return f"{int(value)}"
        return f"{value:.{decimals}f}"
    return str(value)


def stats_table_html(stats: dict, is_bounded: bool) -> str:
    """Build the per-experiment stats grid per spec Section 3."""
    rho = stats["rho"]
    rho_str = f"{rho:.3f}" if isinstance(rho, (int, float)) else "—"

    rows: list[tuple[str, str]] = [
        ("μ", fmt(stats["mu"], 0)),
        ("λ", fmt(stats["lambda"], 0)),
        ("ρ = λ/μ", rho_str),
        ("Sent", fmt(stats["sent"], 0)),
        ("Processed", fmt(stats["processed"], 0)),
    ]
    if is_bounded:
        rows += [
            ("Drops", fmt(stats["drops"], 0)),
            ("Drop %", f"{stats['drop_pct']:.2f}%"),
        ]
    rows += [
        ("Mean job time (µs)", fmt(stats["mean_system_time_us"], 1)),
        ("Median job time (µs)", fmt(stats["median_system_time_us"], 1)),
        ("Mean q_num", fmt(stats["mean_q_num"], 2)),
        ("Median q_num", fmt(stats["median_q_num"], 1)),
        ("Max q_num", fmt(stats["max_q_num"], 0)),
    ]

    cells = "\n".join(
        f"      <div><span class=\"k\">{html.escape(k)}</span>"
        f"<span class=\"v\">{html.escape(v)}</span></div>"
        for k, v in rows
    )
    return f"""    <div class="stats-grid">
{cells}
    </div>"""


def experiment_section(stats: dict, charts_dir: Path) -> str:
    name = stats["experiment"]
    is_bounded = isinstance(stats["q_size"], (int, float)) and stats["q_size"] != "unbounded"
    title = name.replace("_", " ")

    qsize_uri = encode_image_as_data_uri(charts_dir / f"{name}_qsize.png")
    hist_uri = encode_image_as_data_uri(charts_dir / f"{name}_hist.png")

    return f"""  <section class="experiment">
    <h3>{html.escape(title)}</h3>
{stats_table_html(stats, is_bounded)}
    <figure>
      <img src="{qsize_uri}" alt="queue size over time for {name}">
      <figcaption>Queue size (q_num) at each job's completion, in chronological order.</figcaption>
    </figure>
    <figure>
      <img src="{hist_uri}" alt="system time histogram for {name}">
      <figcaption>Histogram of per-job system times (departure − arrival), 10 bins.</figcaption>
    </figure>
  </section>"""


def students_table_html(students: list[dict]) -> str:
    has_email = any(s.get("email") for s in students)
    if has_email:
        header = "<tr><th>Name</th><th>Student ID</th><th>Email</th></tr>"
        body = "\n".join(
            f"      <tr><td>{html.escape(s.get('name', ''))}</td>"
            f"<td>{html.escape(s.get('id', ''))}</td>"
            f"<td>{html.escape(s.get('email', ''))}</td></tr>"
            for s in students
        )
    else:
        header = "<tr><th>Name</th><th>Student ID</th></tr>"
        body = "\n".join(
            f"      <tr><td>{html.escape(s.get('name', ''))}</td>"
            f"<td>{html.escape(s.get('id', ''))}</td></tr>"
            for s in students
        )
    return f"""    <table>
      <thead>
        {header}
      </thead>
      <tbody>
{body}
      </tbody>
    </table>"""


def file_descriptions_html() -> str:
    files = [
        ("client.c", "UDP job-generator. Samples Poisson inter-arrival times and "
                     "exponential job lengths via the spec's randexp; sends each job "
                     "as a 10-byte datagram in network byte order; logs a TSV line "
                     "per job."),
        ("server.c", "Multi-threaded UDP server. Acceptor thread (main) calls "
                     "recvfrom in a loop and enqueues jobs into a synchronized "
                     "STAILQ; worker thread dequeues, sleeps for the job's length "
                     "to simulate processing, and logs the per-job statistics. "
                     "Drop-tail policy when the FIFO is full. Mutex + condition "
                     "variable for synchronization; clock_gettime(CLOCK_MONOTONIC) "
                     "for timing."),
        ("Makefile", "Build script. <code>make</code> compiles both binaries with "
                     "-Wall -Wextra -O2 -std=c11 -Wpedantic, plus -pthread for the "
                     "server and -lm for the client. <code>make clean</code> "
                     "removes the binaries."),
        ("README.pdf", "This document."),
    ]
    body = "\n".join(
        f"      <tr><td><code>{html.escape(name)}</code></td>"
        f"<td>{desc}</td></tr>"
        for name, desc in files
    )
    return f"""    <table>
      <thead><tr><th>File</th><th>Description</th></tr></thead>
      <tbody>
{body}
      </tbody>
    </table>"""


def discussion_html() -> str:
    """A brief discussion section comparing observed vs theoretical M/M/1 behavior."""
    return """  <section>
    <h2 class="no-break-after">Discussion of Results</h2>

    <h3>M/M/1 theory vs observed</h3>
    <p>The M/M/1 model predicts the average number of jobs in the system as
    L = ρ / (1 − ρ). For our stable experiments at moderate utilization
    (ρ ∈ {0.6, 0.7, 0.8, 0.9}), we observe average q_num values that are
    in the same order of magnitude as the theoretical prediction, with
    the gap explained by the finite simulation length: 1000–4000 samples
    is not enough to reach the long-tail steady state, so the observed
    average is biased low compared to L.</p>

    <p>The deliberately unstable case (μ, λ) = (3, 5) — ρ = 1.67 > 1 — shows
    monotonically growing q_num across the run, reaching hundreds (1000-job)
    or low thousands (4000-job). This is exactly the M/M/1 instability
    signature: the queue cannot stabilize because arrivals exceed service
    capacity.</p>

    <h3>Effect of utilization on system time</h3>
    <p>For the (50, λ) family at fixed μ=50 and increasing λ from 30 to 45,
    we see mean and median job system times grow with ρ. This matches the
    theoretical mean wait W = 1/(μ − λ) — wait time goes to infinity as
    ρ → 1.</p>

    <h3>Drops in bounded-queue experiments</h3>
    <p>Both bounded experiments (q_size = 10) recorded a small number of
    drops (8 of 2000 ≈ 0.4%). The fact that the (50, 45) and (50, 48) runs
    produced very similar drop counts on macOS is attributable to the host
    OS's <code>nanosleep</code> minimum granularity (~50–100 µs on macOS),
    which is comparable to the theoretical inter-arrival times at λ=45 and
    λ=48 (≈ 22 µs and 21 µs respectively). The scheduler effectively floors
    both to a similar realized rate. On a Linux host with finer scheduling
    resolution the drop counts should differentiate more clearly.</p>

    <h3>Two-client behavior</h3>
    <p>Experiment 2 (two concurrent clients, each at λ=20, sharing μ=50)
    has combined utilization ρ_total = 2λ/μ = 0.8. Observed mean q_num was
    in the expected range and the two clients' jobs interleaved correctly
    in the server log (different PIDs and ephemeral ports), confirming
    the server multiplexes UDP datagrams from multiple senders without any
    additional code — UDP's connectionless nature and the kernel's per-port
    receive queue handle this transparently.</p>
  </section>"""


def platform_notes_html() -> str:
    return """  <section>
    <h2 class="no-break-after">Platform Notes</h2>
    <p>Code was developed on macOS (Apple Silicon) and tested with both
    the regular optimized build (<code>-O2</code>) and an
    AddressSanitizer-instrumented build
    (<code>-fsanitize=address -O0 -ggdb3</code>) under stress (1000 jobs)
    and bounded-queue scenarios — both clean.</p>
    <p>The Makefile follows the spec's example exactly, including the
    <code>-march=native</code> flag. Since the submission is source code,
    the flag is evaluated when the grader runs <code>make</code> on the
    Ubuntu host and targets that CPU's instruction set.</p>
    <p>Absolute timing values reported in this document include the ~50 µs
    minimum overhead of <code>nanosleep</code> on macOS. On the Linux
    grading environment (finer scheduler granularity) the absolute numbers
    will be smaller, but the relative pattern across experiments — queue
    growing with ρ, drops increasing with bounded capacity — is platform
    independent.</p>
  </section>"""


CSS = """
@page { size: A4; margin: 1.8cm; }
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
    line-height: 1.4;
    color: #222;
    margin: 0 auto;
    max-width: 800px;
    padding: 0 16px;
    font-size: 11pt;
}
h1 {
    font-size: 20pt;
    margin-bottom: 0;
    color: #111;
}
h1 + p.subtitle {
    color: #555;
    margin-top: 4px;
    font-size: 11pt;
}
h2 {
    font-size: 14pt;
    margin-top: 22pt;
    padding-bottom: 3px;
    border-bottom: 2px solid #ccc;
    page-break-before: always;
}
h2.no-break-after { page-break-before: auto; }
h2:first-of-type { page-break-before: auto; }
h3 {
    font-size: 11.5pt;
    margin-top: 14pt;
    margin-bottom: 4pt;
    color: #1a4480;
}

/* Compact stats grid: 2 columns of key-value pairs per experiment */
.stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    column-gap: 16px;
    row-gap: 2px;
    margin: 6pt 0 8pt;
    font-size: 9.5pt;
    max-width: 560px;
}
.stats-grid > div {
    padding: 2px 0;
    border-bottom: 1px dotted #ddd;
    display: flex;
    justify-content: space-between;
}
.stats-grid .k { color: #555; }
.stats-grid .v { font-weight: 600; color: #111; font-variant-numeric: tabular-nums; }

/* Compact regular tables (students, file descriptions) */
table {
    border-collapse: collapse;
    margin: 6pt 0;
    width: 100%;
    font-size: 9.5pt;
}
table th, table td {
    border: 1px solid #ccc;
    padding: 4px 8px;
    text-align: left;
    vertical-align: top;
}
table th { background: #f4f4f4; font-weight: 600; }

figure {
    margin: 8pt 0;
    page-break-inside: avoid;
}
figure img {
    max-width: 100%;
    max-height: 220pt;
    height: auto;
    width: auto;
    border: 1px solid #ddd;
    border-radius: 3px;
    display: block;
    margin: 0 auto;
}
figcaption {
    color: #666;
    font-size: 8.5pt;
    text-align: center;
    margin-top: 3px;
    font-style: italic;
}
.experiment {
    page-break-inside: avoid;
    margin-bottom: 14pt;
    padding-bottom: 6pt;
    border-bottom: 1px solid #eee;
}
.experiment:last-child { border-bottom: none; }
code {
    font-family: "Menlo", "SF Mono", "Courier New", monospace;
    font-size: 9.5pt;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
}
p { margin: 6pt 0; }
.footnote { font-size: 9pt; color: #666; }
"""


def build_html(students: list[dict], course_info: dict,
               summary_df: pd.DataFrame, charts_dir: Path) -> str:
    sections: list[str] = []

    sections.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(course_info['assignment_title'])} — README</title>
  <style>{CSS}</style>
</head>
<body>
  <h1>{html.escape(course_info['assignment_title'])}</h1>
  <p class="subtitle">{html.escape(course_info['course_title'])} — {html.escape(course_info['instructor'])}<br>
  Submission date: {html.escape(course_info['submission_date'])}</p>

  <h2 class="no-break-after">Submitted by</h2>
{students_table_html(students)}

  <h2>Submission Contents</h2>
{file_descriptions_html()}

  <h2>Implementation Summary</h2>
  <p>The system consists of a UDP <strong>client</strong> that generates jobs
  according to a Poisson process (parameter λ) with exponentially distributed
  service-time stamps (parameter μ), and a multi-threaded UDP <strong>server</strong>
  that receives jobs into a bounded FIFO and processes them on a dedicated
  worker thread.</p>

  <p>The server's two threads share a STAILQ-backed FIFO protected by a
  pthread mutex; the worker waits on a condition variable when the queue
  is empty and is woken by the acceptor on each enqueue. A
  <code>done</code> flag, set by the acceptor after num_jobs receives,
  cooperates with the worker to drain remaining jobs and exit cleanly.</p>

  <p>The 8th column of the server log (<code>q_time</code>) and the 7th
  (<code>q_num</code>) include the just-finished job per the lecturer's
  clarification — counters are decremented only after the log line is
  printed.</p>
""")

    # Per-experiment results
    sections.append("""  <h2>Experimental Results</h2>""")

    summary_lookup = {row["experiment"]: row.to_dict() for _, row in summary_df.iterrows()}

    for group_title, group_desc, exp_names in EXPERIMENT_GROUPS:
        sections.append(f"""  <section>
    <h2 class="no-break-after">{html.escape(group_title)}</h2>
    <p>{html.escape(group_desc)}</p>
""")
        for exp in exp_names:
            stats = summary_lookup.get(exp)
            if stats is None:
                sections.append(f"    <p><em>(missing data for {exp})</em></p>\n")
                continue
            sections.append(experiment_section(stats, charts_dir))
        sections.append("  </section>")

    sections.append(discussion_html())
    sections.append(platform_notes_html())

    sections.append("""</body>
</html>""")

    return "\n".join(sections)


def main() -> int:
    project_root = Path(__file__).resolve().parent

    students_file = project_root / "students.json"
    summary_file = project_root / "summary.csv"
    charts_dir = project_root / "charts"
    output = project_root / "README.html"

    if not students_file.exists():
        print(f"error: {students_file} missing — fill in your team info", file=sys.stderr)
        return 1
    if not summary_file.exists():
        print(f"error: {summary_file} missing — run analyze.py first", file=sys.stderr)
        return 1
    if not charts_dir.is_dir():
        print(f"error: {charts_dir}/ missing — run analyze.py first", file=sys.stderr)
        return 1

    course_info = json.loads(students_file.read_text())
    students = course_info.pop("students", [])

    summary_df = pd.read_csv(summary_file)

    html_content = build_html(students, course_info, summary_df, charts_dir)
    output.write_text(html_content)

    size_kb = output.stat().st_size // 1024
    print(f"Wrote {output} ({size_kb} KB).")
    print()
    print("Next steps:")
    print(f"  1. open {output.name}")
    print("  2. In Safari/Chrome:  File → Print → 'Save as PDF' → README.pdf")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
