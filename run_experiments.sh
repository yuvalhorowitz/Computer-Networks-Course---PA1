#!/bin/bash
# run_experiments.sh
#
# Automates all 12 PA1 experiments specified in Section 3 of the assignment.
# Saves each run's output to results/<name>_{server,client[_a|_b]}.tsv.
#
# Usage:
#   ./run_experiments.sh
#
# Environment variables (optional overrides):
#   SEED      — base seed for the RNG (default 42; second client uses SEED+1)
#   PORT_BASE — first UDP port to use (default 9000); each experiment uses BASE+i

set -euo pipefail

SEED=${SEED:-42}
PORT_BASE=${PORT_BASE:-9000}
HOST=127.0.0.1
RESULTS=results
EXP_INDEX=0

mkdir -p "$RESULTS"

echo ">>> Building binaries..."
make >/dev/null
echo

# run_single <name> <num_jobs> <mu> <lambda> <q_size>
# Runs one server + one client. Records output to results/<name>_{server,client}.tsv.
run_single() {
    local name=$1 num=$2 mu=$3 lam=$4 q=$5
    local port=$((PORT_BASE + EXP_INDEX))
    EXP_INDEX=$((EXP_INDEX + 1))

    printf "[%2d] %-32s port=%d  num=%5d  mu=%-3d  lam=%-3d  q=%-5d  ...  " \
           "$EXP_INDEX" "$name" "$port" "$num" "$mu" "$lam" "$q"

    ./server "$port" "$num" "$q" > "$RESULTS/${name}_server.tsv" &
    sleep 0.3
    ./client "$HOST" "$port" "$num" "$SEED" "$lam" "$mu" > "$RESULTS/${name}_client.tsv"
    wait

    local sent got drops
    sent=$(wc -l < "$RESULTS/${name}_client.tsv")
    got=$(wc -l < "$RESULTS/${name}_server.tsv")
    drops=$((sent - got))
    printf "sent=%d got=%d drops=%d\n" "$sent" "$got" "$drops"

    sleep 0.2
}

# run_two <name> <num_per_client> <mu> <lambda> <q_size>
# Runs one server + two concurrent clients (each sends num_per_client jobs).
run_two() {
    local name=$1 num=$2 mu=$3 lam=$4 q=$5
    local port=$((PORT_BASE + EXP_INDEX))
    EXP_INDEX=$((EXP_INDEX + 1))
    local total=$((num * 2))

    printf "[%2d] %-32s port=%d  2x%d  mu=%-3d  lam=%-3d  q=%-5d  ...  " \
           "$EXP_INDEX" "$name" "$port" "$num" "$mu" "$lam" "$q"

    ./server "$port" "$total" "$q" > "$RESULTS/${name}_server.tsv" &
    sleep 0.3
    ./client "$HOST" "$port" "$num" "$SEED"       "$lam" "$mu" > "$RESULTS/${name}_client_a.tsv" &
    ./client "$HOST" "$port" "$num" $((SEED + 1)) "$lam" "$mu" > "$RESULTS/${name}_client_b.tsv" &
    wait

    local sa sb got
    sa=$(wc -l < "$RESULTS/${name}_client_a.tsv")
    sb=$(wc -l < "$RESULTS/${name}_client_b.tsv")
    got=$(wc -l < "$RESULTS/${name}_server.tsv")
    printf "sent=%d+%d=%d got=%d drops=%d\n" "$sa" "$sb" "$((sa + sb))" "$got" "$((sa + sb - got))"

    sleep 0.2
}

echo ">>> Experiment 1: single client, unbounded queue"
run_single "exp1_mu5_lam3_n1000"     1000   5   3   2000
run_single "exp1_mu5_lam3_n4000"     4000   5   3   8000
run_single "exp1_mu3_lam5_n1000"     1000   3   5   2000
run_single "exp1_mu3_lam5_n4000"     4000   3   5   8000
run_single "exp1_mu50_lam30_n1000"   1000   50  30  2000
run_single "exp1_mu50_lam30_n4000"   4000   50  30  8000
run_single "exp1_mu50_lam35_n2000"   2000   50  35  4000
run_single "exp1_mu50_lam40_n2000"   2000   50  40  4000
run_single "exp1_mu50_lam45_n2000"   2000   50  45  4000

echo
echo ">>> Experiment 2: two clients, unbounded queue"
run_two    "exp2_mu50_lam20_2x2000"  2000   50  20  8000

echo
echo ">>> Experiment 3: bounded queue (q_size=10)"
run_single "exp3_mu50_lam45_q10"     2000   50  45  10
run_single "exp3_mu50_lam48_q10"     2000   50  48  10

echo
echo ">>> All done. Outputs in $RESULTS/"
ls -1 "$RESULTS/" | sort
