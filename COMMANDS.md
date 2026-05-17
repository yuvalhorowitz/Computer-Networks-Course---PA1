# Commands Reference — PA1

Quick copy-paste reference for build, run, test, and experiment commands.

---

## Build

### Build everything

```bash
make
```
Builds both `client` and `server` (server won't build until we write it).

### Build just the client

```bash
make client
```

### Build just the server

```bash
make server
```

### Clean build artifacts

```bash
make clean
```
Removes `client` and `server` executables.

### Direct gcc invocation (without Makefile)

```bash
# Client
gcc -Wall -Wextra -O2 -std=c11 -Wpedantic -o client client.c -lm

# Server (when written)
gcc -Wall -Wextra -O2 -std=c11 -Wpedantic -pthread -o server server.c
```

---

## Run client

### Show usage (no args)

```bash
./client
```
Expected output (stderr):
```
Usage: ./client ip port num_jobs seed lambda mu
```
Exit code: 1

### Basic run

```bash
./client 127.0.0.1 9000 10 42 5.0 3.0
```
- Send 10 jobs to localhost:9000
- Seed 42, λ=5, μ=3
- Currently does nothing (loop not implemented yet)

### Run client and see TSV output (loop implemented)

```bash
./client 127.0.0.1 9000 10 42 50.0 20.0
```
Expected: 10 lines on stdout in TSV format. Takes roughly num_jobs/lambda seconds (here 10/50 = 0.2s). Example line:
```
7f000001:2328	12345:0	17234	8921
```
(`12345` is your shell PID — will differ for you.)

### Confirm sendto error handling works (no server listening is fine for UDP — packets just go into the void)

```bash
./client 127.0.0.1 9000 5 42 1000.0 1000.0
```
Should still print 5 TSV lines and exit 0. UDP doesn't care if the destination port has a listener.

### Test invalid port

```bash
./client 127.0.0.1 99999 10 42 5.0 3.0
```
Expected output (stderr): `invalid port: 99999`
Exit code: 1

### Test invalid IP

```bash
./client not.an.ip 9000 10 42 5.0 3.0
```
Expected output (stderr): `invalid ip: not.an.ip`
Exit code: 1

### Test invalid lambda (must be > 0)

```bash
./client 127.0.0.1 9000 10 42 0 3.0
```
Expected output (stderr): `invalid lambda: 0`
Exit code: 1

### Redirect TSV log to file (once loop is implemented)

```bash
./client 127.0.0.1 9000 128 211 50.0 20.0 > client.tsv
```

---

## Run server

### Show usage (no args)

```bash
./server
```
Expected output (stderr): `Usage: ./server port num_jobs q_size`, exit 1

### Test invalid num_jobs

```bash
./server 9000 abc 50
```
Expected: `invalid num_jobs: abc`, exit 1

### Test invalid port

```bash
./server 99999 100 50
```
Expected: `invalid port: 99999`, exit 1

### Basic run (only arg parsing implemented so far — exits immediately)

```bash
./server 9000 10 100 > server.tsv
```
- Bind to port 9000
- Expect 10 total jobs
- FIFO capacity = 100

---

## Testing combined client + server

### Quick smoke test (single line, all in one terminal)

```bash
./server 9000 5 100 > server.tsv & sleep 0.5; ./client 127.0.0.1 9000 5 42 50.0 20.0 > client.tsv; wait
echo "--- server.tsv ---"; cat server.tsv
echo "--- client.tsv ---"; cat client.tsv
```

Expected: 5 lines in each file. Server lines look like:
```
7f000001:abcd	12345:0	307163	324003	1	2740
```

### One client, one server (two terminals)

```bash
# Terminal 1
./server 9000 10 100 > server.tsv

# Terminal 2
./client 127.0.0.1 9000 10 42 5.0 3.0 > client.tsv
```

### Background server, foreground client

```bash
./server 9000 10 100 > server.tsv &
sleep 0.5
./client 127.0.0.1 9000 10 42 5.0 3.0 > client.tsv
wait
```

---

## Debug / verify

### Check we're not leaking memory (Linux)

```bash
valgrind --leak-check=full --show-leak-kinds=all ./client 127.0.0.1 9000 10 42 5.0 3.0
```

### AddressSanitizer build

```bash
gcc -Wall -Wextra -O0 -ggdb3 -std=c11 -Wpedantic \
    -fsanitize=address -fsanitize=pointer-compare -fsanitize=pointer-subtract \
    -o client_asan client.c -lm
```

### Check what's listening on a port (macOS / Linux)

```bash
lsof -i :9000        # macOS
ss -tulpen | grep 9000   # Linux
```

### Listen on a UDP port without our server (for debugging client output)

```bash
nc -u -l 9000        # listens for UDP on port 9000, prints whatever arrives
```
Useful to verify the client is actually sending packets even before we have a server.

### Hexdump received UDP traffic on a port

```bash
nc -u -l 9000 | xxd
```

---

## Experiments

*(To be filled in when run_experiments.sh is written)*

### Run all experiments

```bash
./run_experiments.sh
```

### Single experiment example (placeholder)

```bash
./server 9000 1000 10000 > results/exp1_mu5_lam3_n1000.tsv &
./client 127.0.0.1 9000 1000 42 3.0 5.0 > /dev/null
wait
```

### Analyze results

```bash
python3 analyze.py results/
```

---

## Git

### Stage and commit changes

```bash
git add <files>
git commit -m "your message"
```

### Push to GitHub

```bash
git push -u origin main
```
*Note: GitHub may be blocked by sandbox. If so, run with `! git push` from Claude Code to execute in your shell.*
