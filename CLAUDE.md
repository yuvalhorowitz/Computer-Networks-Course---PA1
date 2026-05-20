# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Programming Assignment 1 for Computer Networks 512.4662 (Tel Aviv University, Prof. Patt-Shamir). Implement a UDP client-server queuing system simulating an M/M/1 queue.

## Reference Materials (`source files/`)

- `Programming assignment 1.pdf` — Full assignment spec
- `Socket programming.pdf` — Beej's Guide to Network Programming (socket API reference)
- `netCalBook.pdf` — Network Calculus textbook (queuing theory background)
- `server1b-1.tsv` — Example server output (2000 lines, for validation)

## Language and Environment

- Language: **C11** (C++ allowed but C preferred)
- Target platform: **Ubuntu 22.04 LTS** (graded on Ubuntu)
- Development on macOS is fine but final testing must be on Linux
- POSIX APIs: sockets, pthreads, clock_gettime, nanosleep

## Build

```makefile
CC= gcc
CFLAGS= -Wall -Wextra -O2 -std=c11 -Wpedantic -march=native

all: server client
.PHONY: all clean

server: server.c
	$(CC) $(CFLAGS) -pthread -o server server.c

client: client.c
	$(CC) $(CFLAGS) -o client client.c -lm

clean:
	rm -f server client
```

`-march=native` is in the spec's example Makefile (Section 5). Since the grader compiles from source on their Ubuntu machine, the flag picks up *their* CPU's instruction set — exactly as intended.

## Architecture

### Files to Create

```
├── client.c            # UDP job generator
├── server.c            # Multi-threaded UDP server with bounded FIFO queue
├── Makefile            # Build system
├── run_experiments.sh  # Automates all experiments
└── analyze.py          # Statistics + charts for README.pdf
```

### client.c

**Command**: `./client ip port num_jobs seed lambda mu`

- Generates jobs with Poisson inter-arrival (param lambda) and exponential lengths (param mu)
- For each job: sample x=randexp(lambda), sleep floor(x*1e6) ns, sample y=randexp(mu), send UDP datagram, log TSV
- Wire format (10 bytes, network byte order): client_id (uint32) | job_index (uint16) | job_length (uint32)
- RNG: `srand(seed)`, then alternating rand() calls — first for x, then for y, per iteration
- TSV output: `"%08x:%04x\t%d:%d\t%d\t%d\n"`

### server.c

**Command**: `./server port num_jobs q_size`

- Two threads: **acceptor** (main, recvfrom loop) and **worker** (spawned, dequeue+sleep)
- Queue: `<sys/queue.h>` STAILQ, bounded by q_size, drop-tail policy
- Synchronization: pthread mutex + condition variable
- Timing: `clock_gettime(CLOCK_MONOTONIC)`, log in microseconds
- Acceptor counts ALL received jobs (including dropped) toward num_jobs
- Worker processes remaining queue after acceptor finishes, then exits
- TSV output: `"%08x:%04x\t%d:%d\t%ld\t%ld\t%d\t%ld\n"`

### Key Implementation Details

- `randexp(lambda)`: `double u = rand() / ((double)RAND_MAX + 1.0); return -log(1.0 - u) / lambda;`
- Network byte order: `htonl()`/`htons()` on send, `ntohl()`/`ntohs()` on receive
- Worker shutdown: loop exits only when queue empty AND done flag set
- Memory: malloc each job on receive, free after processing (or on drop)
- Errors: log to stderr with `perror()`, exit non-zero, close all sockets

### q_num / q_time Semantics (lecturer clarification)

- **q_num** = total jobs in the SYSTEM (arrived but not finished), NOT just FIFO waiters
- **The just-finished job IS included** in its own log line's q_num and q_time
- Implementation: maintain `jobs_in_system` counter; log line first, decrement after
- Sanity check: `server1b-1.tsv` job 0 has q_num=1 (the job itself, with no others queued)

## Experiments

1. **Single client, unbounded queue**: (μ,λ)=(5,3),(3,5),(50,30) × {1000,4000} jobs; (50,35),(50,40),(50,45) × 2000 jobs
2. **Two clients, unbounded queue**: 2×2000 jobs, (μ,λ)=(50,20)
3. **Bounded queue** (q_size=10): 2000 jobs, (μ,λ)=(50,45),(50,48)

Statistics per experiment: avg/median job time, avg/median queue occupancy, drop count (bounded only), queue-size-over-time chart, system-time histogram (10 bins).

## Verification

1. `make` — no warnings on macOS and Linux
2. Run server+client with 10 jobs, verify TSV format matches spec
3. Valgrind: `valgrind --leak-check=full ./server ...` — no leaks
4. AddressSanitizer: recompile with `-fsanitize=address`
5. Statistical check: avg service ≈ 1e6/mu, avg inter-arrival ≈ 1e6/lambda
6. Bounded queue: drop count = jobs sent by client − lines in server output

## Platform Notes

| Concern | Solution |
|---|---|
| `<sys/queue.h>` | Available on macOS and Linux |
| `clock_gettime(CLOCK_MONOTONIC)` | macOS 10.12+ and Linux |
| `pthread` | `-pthread` flag (both platforms) |
| `nanosleep`, `inet_pton` | POSIX, both platforms |
| Byte order | macOS ARM = little-endian like x86 Linux |

Pre-submission: compile and test on Ubuntu 22.04 (WSL/VM), run Valgrind + ASan.
