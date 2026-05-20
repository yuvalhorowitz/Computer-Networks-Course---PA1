# Remaining Tasks — PA1

This file tracks what's left to complete and submit the assignment.

**Current status**: `client.c`, `server.c`, and `Makefile` implemented and smoke-tested with 5 jobs. Both build cleanly with `-Wall -Wextra -O2 -std=c11 -Wpedantic`.

---

## Phase 1 — Validation & Stress Testing

Goal: prove the implementation is correct before relying on it for full experiments.

- [ ] **Larger run (single client, single server)**: 1000 jobs, e.g. `./server 9000 1000 10000` + `./client 127.0.0.1 9000 1000 42 50.0 20.0`. Confirm both terminate and `wc -l server.tsv` is exactly 1000.
- [ ] **Bounded-queue test**: small `q_size` (e.g. 10) with high arrival rate (μ=50, λ=48) for 200 jobs. Confirm drops occur: `expr <client_lines> - <server_lines>` should be > 0.
- [ ] **Two-client test (Experiment 2)**: `./server 9000 4000 10000 &; ./client 127.0.0.1 9000 2000 42 50.0 20.0 & ./client 127.0.0.1 9000 2000 99 50.0 20.0 &; wait`. Server should produce 4000 lines mixing both clients' PIDs.
- [ ] **Statistical sanity**: avg service time ≈ 1e6/μ; avg inter-arrival ≈ 1e6/λ. Quick awk one-liner on the TSV.
- [ ] **AddressSanitizer build**: rebuild with `-fsanitize=address -fsanitize=pointer-compare -fsanitize=pointer-subtract`, run a 1000-job experiment, confirm no errors.
- [ ] **Valgrind on Ubuntu**: `valgrind --leak-check=full --show-leak-kinds=all ./server ...`. Should report zero leaks.
- [ ] **Compile on Ubuntu 22.04** (WSL or VM): the actual grading environment. `make` must succeed with no warnings.

---

## Phase 2 — Experiments (Spec Section 3)

All required runs. Save server output to `results/<name>.tsv`.

### Experiment 1: Single client, unbounded queue
*(use `q_size > num_jobs`, e.g. `num_jobs * 2`)*

- [ ] (μ, λ) = (5, 3), 1000 jobs
- [ ] (μ, λ) = (5, 3), 4000 jobs
- [ ] (μ, λ) = (3, 5), 1000 jobs **[unstable: ρ=1.67]**
- [ ] (μ, λ) = (3, 5), 4000 jobs **[unstable]**
- [ ] (μ, λ) = (50, 30), 1000 jobs
- [ ] (μ, λ) = (50, 30), 4000 jobs
- [ ] (μ, λ) = (50, 35), 2000 jobs
- [ ] (μ, λ) = (50, 40), 2000 jobs
- [ ] (μ, λ) = (50, 45), 2000 jobs

### Experiment 2: Two clients, unbounded queue
- [ ] Two × 2000 jobs, (μ, λ) = (50, 20). Server `num_jobs = 4000`.

### Experiment 3: Single client, bounded queue (q_size = 10)
- [ ] (μ, λ) = (50, 45), 2000 jobs
- [ ] (μ, λ) = (50, 48), 2000 jobs

---

## Phase 3 — Automation & Analysis

- [ ] **`run_experiments.sh`**: shell script that runs all 12 experiments above, saves outputs to `results/expN_*.tsv`. Use unique ports per experiment to avoid TIME_WAIT collisions.
- [ ] **`analyze.py`**: Python script (matplotlib + numpy or pandas) that for each experiment computes:
  - [ ] Average and median job system time (departure − arrival)
  - [ ] Average and median queue occupancy (q_num column)
  - [ ] Drop count and percentage (bounded experiments only): `client_jobs - server_lines`
  - [ ] Queue-size-over-time chart (q_num vs index or arrival)
  - [ ] System-time histogram, 10 bins
- [ ] Output directory layout: `charts/exp1a_mu5_lam3_n1000_qsize.png`, `charts/exp1a_mu5_lam3_n1000_hist.png`, etc.
- [ ] Summary table: a single CSV (or markdown table) with all stats across all experiments — easier to drop into the README.

---

## Phase 4 — README.pdf (Spec Section 4)

Required contents per the spec:

- [ ] **Students' names, IDs, and email addresses**
- [ ] **Submission contents** (file descriptions: server.c, client.c, Makefile, README.pdf)
- [ ] **For each experiment**:
  - [ ] All statistics (avg/median job time, avg/median queue occupancy, drops if applicable)
  - [ ] Queue size over time chart
  - [ ] Histogram of job system times (10 bins)
- [ ] Optional but useful: brief discussion of M/M/1 expected vs observed (e.g., utilization ρ, expected mean queue size from Little's law).
- [ ] Tooling: write in LaTeX, Markdown→PDF (pandoc), Google Docs, or anything that produces a PDF.

---

## Phase 5 — Pre-submission Verification

Cross-checks before zipping.

- [ ] `make` clean on **Ubuntu 22.04** (WSL or VM) — zero warnings.
- [ ] **No `-march=native` in Makefile** (Apple Silicon dev → Ubuntu x86 portability).
- [ ] Sample run on Ubuntu reproduces results (statistical, not byte-exact — different timing).
- [ ] Valgrind: zero leaks across all experiment configurations.
- [ ] AddressSanitizer: zero errors.
- [ ] Function-level documentation (each function has a doc comment per spec Section 4).
- [ ] Output format byte-for-byte matches spec format strings.
- [ ] Inline review of error paths: every `malloc` checked, every syscall checked, every socket closed, every mutex/cond destroyed.

---

## Phase 6 — Submission (Spec Section 5)

- [ ] Naming: `PA1_<ID1>_<ID2>.zip`
- [ ] Contents (and ONLY these):
  - [ ] `server.c`
  - [ ] `client.c`
  - [ ] `Makefile`
  - [ ] `README.pdf`
- [ ] **Do NOT include**: binaries, .tsv outputs, source files folder, .git, charts (charts go INSIDE the README.pdf).
- [ ] Upload to Moodle.

---

## Notes for self

- **Reproducibility**: same seed + same parameters must produce same client TSV. Use this in the analyze script for sanity.
- **Sandbox limits during dev**: `bind`/`sendto` get blocked from Claude Code's tool sandbox. Test in your real terminal with `! <cmd>` or by running the binaries yourself.
- **TIME_WAIT**: `SO_REUSEADDR` is set, so quick restarts are fine. Still, vary ports across concurrent experiments to avoid contention.
- **GitHub push blocked from sandbox**: run `git push` in your own terminal.
