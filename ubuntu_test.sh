#!/bin/bash
# ubuntu_test.sh
#
# Runs Phase 1.6 + 1.7 verification inside an Ubuntu 22.04 Docker container:
#   * Compile from source with the spec's exact flags — zero warnings expected.
#   * Run the binary with a small workload, confirm it terminates and produces
#     the right number of lines.
#   * Run Valgrind --leak-check=full --show-leak-kinds=all — zero leaks expected.
#
# Requires: docker (or colima + docker). Run `colima start` first if needed.
#
# Usage:
#   ./ubuntu_test.sh

set -euo pipefail

if ! docker info >/dev/null 2>&1; then
    echo "error: docker daemon not reachable." >&2
    echo "If you installed colima, run: colima start" >&2
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ">>> Project: $PROJECT_DIR"
echo ">>> Pulling ubuntu:22.04 (first time only)..."
docker pull ubuntu:22.04

echo ""
echo ">>> Running tests inside Ubuntu 22.04 container..."
docker run --rm \
    -v "$PROJECT_DIR":/work \
    -w /work \
    ubuntu:22.04 bash -c '
set -euo pipefail

echo "=== Installing build tools ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends gcc make libc-dev valgrind > /dev/null 2>&1
gcc --version | head -1
echo "valgrind: $(valgrind --version)"
echo

echo "=== Phase 1.7: clean compile under spec flags ==="
make clean
if make 2>&1 | tee /tmp/make.log; then
    echo
    if grep -qE "warning:" /tmp/make.log; then
        echo "❌ Build had warnings (see above)" >&2
        exit 1
    else
        echo "✅ Phase 1.7 PASS: no warnings"
    fi
else
    echo "❌ Build failed" >&2
    exit 1
fi
echo

echo "=== Sanity smoke test: 100 jobs, single client ==="
./server 9100 100 1000 > /tmp/srv.tsv & SERVER_PID=$!
sleep 0.3
./client 127.0.0.1 9100 100 42 30 50 > /tmp/cli.tsv
wait $SERVER_PID
SLINES=$(wc -l < /tmp/srv.tsv)
CLINES=$(wc -l < /tmp/cli.tsv)
echo "  client lines: $CLINES"
echo "  server lines: $SLINES"
if [ "$SLINES" -eq 100 ] && [ "$CLINES" -eq 100 ]; then
    echo "✅ Smoke test PASS"
else
    echo "❌ Smoke test FAIL: expected 100/100, got $CLINES/$SLINES" >&2
    exit 1
fi
head -1 /tmp/srv.tsv
echo

echo "=== Phase 1.6: Valgrind on server (most interesting — handles all malloc/free) ==="
# Server has more interesting memory traffic than client (malloc per job,
# free on drop, free after worker logs). We run valgrind only on the
# server. Workload is intentionally small (50 jobs, low arrival rate) so
# the run stays in the seconds-not-minutes range under valgrind (which
# is roughly 10x slower than native). The bounded queue (q=5) plus a
# fast service (mu=50) and aggressive arrival (lambda=100) intentionally
# induces drops to exercise the acceptor-side free path.

# Start server under valgrind FIRST (give it 3 sec to launch — valgrind
# is slow to start). Then run client.
valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes \
         --error-exitcode=42 \
    ./server 9102 50 5 > /tmp/srv3.tsv 2> /tmp/vg_server.log &
VG_PID=$!
sleep 3   # generous startup margin — valgrind takes 1-3 sec to start

./client 127.0.0.1 9102 50 42 100 50 > /tmp/cli3.tsv 2>/dev/null
CLIENT_RC=$?

# Wait for valgrind+server to drain and exit
wait $VG_PID
VG_RC=$?

echo "  client exit code: $CLIENT_RC"
echo "  client lines:     $(wc -l < /tmp/cli3.tsv)"
echo "  server lines:     $(wc -l < /tmp/srv3.tsv)"
echo "  drops:            $(($(wc -l < /tmp/cli3.tsv) - $(wc -l < /tmp/srv3.tsv)))"
echo
echo "--- Valgrind summary ---"
grep -E "ERROR SUMMARY|definitely lost|indirectly lost|possibly lost|still reachable" \
     /tmp/vg_server.log || tail -10 /tmp/vg_server.log
echo
if [ "$VG_RC" -eq 0 ]; then
    echo "✅ Phase 1.6 PASS: Valgrind reported zero errors and zero leaks"
elif [ "$VG_RC" -eq 42 ]; then
    echo "❌ Phase 1.6 FAIL: Valgrind found errors. Full log saved at /tmp/vg_server.log"
    echo "Last 40 lines of Valgrind output:"
    tail -40 /tmp/vg_server.log
    exit 1
else
    echo "❌ Phase 1.6 FAIL: server exited with rc=$VG_RC"
    tail -40 /tmp/vg_server.log
    exit 1
fi
echo

echo "=== ALL UBUNTU CHECKS PASSED ==="
'
