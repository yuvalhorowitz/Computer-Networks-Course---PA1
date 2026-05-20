# Learning Notes — Computer Networks PA1

A growing reference document mirroring our step-by-step implementation.
Each section corresponds to a **Step** we worked through interactively.
Concepts come first, then the code that uses them.

---

## Table of Contents

- [Step 1: The Makefile](#step-1-the-makefile)
- [Step 2: UDP, Sockets, and Network Addresses](#step-2-udp-sockets-and-network-addresses)
- [Step 3: Queuing Theory — Poisson, Exponential, M/M/1](#step-3-queuing-theory--poisson-exponential-mm1)
- [Step 4: Writing client.c — Skeleton](#step-4-writing-clientc--skeleton)
- [Step 5: Argument Parsing in client.c](#step-5-argument-parsing-in-clientc)
- [Step 6: Seed RNG and Create UDP Socket](#step-6-seed-rng-and-create-udp-socket)
- [Step 7: Main Loop — Byte Order, Sleeping, and Sending](#step-7-main-loop--byte-order-sleeping-and-sending)
- [Step 8: Moving to server.c — Threading Foundation](#step-8-moving-to-serverc--threading-foundation)
- [Step 9: Remaining Server Concepts](#step-9-remaining-server-concepts)
- [Step 10: Writing server.c — Skeleton](#step-10-writing-serverc--skeleton)
- [Step 11: Server Argument Parsing](#step-11-server-argument-parsing)
- [Step 12: Initialize the Queue](#step-12-initialize-the-queue)
- [Step 13: Server Socket — bind, INADDR_ANY, SO_REUSEADDR](#step-13-server-socket--bind-inaddr_any-so_reuseaddr)
- [Step 14: Record t0 and Spawn the Worker Thread](#step-14-record-t0-and-spawn-the-worker-thread)
- [Step 15: The Acceptor Loop](#step-15-the-acceptor-loop)
- [Step 16: The Worker Thread Body](#step-16-the-worker-thread-body)
- [Step 17: The Shutdown Handshake](#step-17-the-shutdown-handshake)
- [Step 18: q_num vs q_time vs Duration — What Each Measures](#step-18-q_num-vs-q_time-vs-duration--what-each-measures)
- *(more sections will be added as we go)*

---

## Step 1: The Makefile

### Concept: How does C code become a program?

C is a **compiled** language. Your `.c` source files go through:

```
   client.c ──[ compiler ]──► machine code ──[ linker ]──► ./client
                                                  ▲
                                       (also pulls in libraries
                                        like libm for log())
```

Two phases:
1. **Compile** — translate human-readable C into CPU instructions.
2. **Link** — combine your code with library code.

### Concept: What is `make`?

`make` reads a `Makefile` describing:
- **What** to build (called *targets*) — e.g., `client`, `server`
- **From what** (called *prerequisites*) — e.g., `client.c`
- **How** (called *recipes*) — the shell commands to run

`make` is also smart: if a source hasn't changed, it won't rebuild.

### Concept: Compiler flags used in PA1

| Flag | What it does | Why we need it |
|---|---|---|
| `-Wall` | Enable all common warnings | Spec requires; catches bugs |
| `-Wextra` | Extra warnings | Catches more subtle bugs |
| `-Wpedantic` | Warn on non-standard C | Spec required; portability |
| `-O2` | Optimize level 2 | Spec required |
| `-std=c11` | Use C11 standard | Course requirement |
| `-pthread` | Enable POSIX threads | Server uses 2 threads |
| `-lm` | Link math library | Client uses `log()` |
| `-march=native` | Optimize for the build host's CPU | In the spec; grader compiles on their Ubuntu host, so it targets that CPU correctly |

**Why we DO use `-march=native`** (and an earlier-version mistake):
- We initially dropped this flag, worrying that "macOS ARM dev → Ubuntu x86 grading" would be an issue.
- That reasoning was wrong: the **submission is source code, not a binary**.
- The grader runs `make` on **their** Ubuntu machine, so `-march=native` targets that CPU correctly — exactly as the spec intends.
- Lesson: if you're shipping source, host-specific compile flags are evaluated at the grader's compile time, not yours.

### Concept: Makefile syntax

```makefile
target: prerequisites
<TAB>recipe-command
```

**Critical**: the recipe line MUST start with a real **TAB character**,
not spaces. The #1 reason beginners' Makefiles break.

Variables:
```makefile
CC = gcc                # convention: CC = "C Compiler"
CFLAGS = -Wall -Wextra  # convention: CFLAGS = "C Flags"
```
Reference as `$(CC)` and `$(CFLAGS)`.

`.PHONY` declares targets that aren't files. Without it, if a file
named `clean` ever existed, `make clean` would do nothing.

### The actual Makefile

```makefile
CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -Wpedantic -march=native

all: server client
.PHONY: all clean

server: server.c
	$(CC) $(CFLAGS) -pthread -o server server.c

client: client.c
	$(CC) $(CFLAGS) -o client client.c -lm

clean:
	rm -f server client
```

### Reference back to assignment

> *Section 5: "The Makefile may look like this:" — followed by similar template.*
> *Section 2.3: "compile with -Wall -Wextra -Wpedantic flags."*

We match the spec, including `-march=native`.

---

## Step 2: UDP, Sockets, and Network Addresses

### Concept: UDP vs TCP

Two transport protocols.

**TCP (Transmission Control Protocol)** — like a phone call.
- Persistent connection between client and server.
- Guarantees: every byte arrives, in order, no duplicates.
- Used for: web (HTTP), file transfer, SSH.

**UDP (User Datagram Protocol)** — like mailing postcards.
- Connectionless. No setup, no guarantee.
- Send a datagram to IP+port; receiver might or might not get it.
- Used for: DNS, video calls, online games.

### Why PA1 uses UDP

> *Spec Section 2: "The communication is carried out via UDP."*

Pedagogical: simpler API. Also fits the scenario — clients fire jobs
at the server, no back-and-forth needed.

### Concept: What is a socket?

A **socket** is the OS abstraction for "an endpoint of network
communication." Think: a file descriptor for the network.

```c
int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
```

- `AF_INET` — Address Family: IPv4 (vs `AF_INET6`)
- `SOCK_DGRAM` — Datagram (UDP); `SOCK_STREAM` would be TCP
- `0` — Default protocol for that combo (UDP)

Returns an integer: the socket file descriptor.

### Client vs server socket usage

| Step | Client (sends) | Server (receives) |
|---|---|---|
| 1. Create | `socket()` | `socket()` |
| 2. Bind to a port | not needed | `bind()` |
| 3. Send/receive | `sendto(addr, data)` | `recvfrom(addr, buf)` |
| 4. Close | `close()` | `close()` |

For UDP:
- Client does NOT call `connect()` (that's TCP). Just `sendto()`.
- Server does NOT call `listen()` or `accept()` (TCP). Just `recvfrom()`.

> *Spec Section 2.2: "the server must still bind() to its address, but
> does not need to call listen() or accept(), and instead calls recvfrom()."*

### Concept: IP + port = network address

A datagram's destination = IP + port.

- **IP**: identifies the machine (e.g., `127.0.0.1` = localhost)
- **Port**: identifies the program on that machine (e.g., `9000`)

In C:
```c
struct sockaddr_in addr;
addr.sin_family = AF_INET;
addr.sin_port = htons(9000);
inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
```

(Byte order details in Step 7.)

---

## Step 3: Queuing Theory — Poisson, Exponential, M/M/1

### Concept: Queuing system parts

```
                    ┌─────────────────────┐
   Jobs arrive ────►│ FIFO queue │ Server │────► Jobs leave
                    │  (waiting) │ (busy) │
                    └─────────────────────┘
```

Three parts:
1. **Arrivals** — jobs appear at random times
2. **Queue** — if server busy, jobs wait
3. **Server** — processes one at a time

PA1 simulates this exactly.

### Concept: M/M/1 notation

- **M** (1st): Markovian arrivals (exponential inter-arrivals)
- **M** (2nd): Markovian service (exponential service times)
- **1**: one server

> *Spec Section 3: "This experiment simulates the basic M/M/1 system."*

### Concept: Poisson arrivals

```
time ───●─────●──●───────●─●──────────●────►
        ↑     ↑  ↑       ↑ ↑          ↑
       job1  job2 job3  job4 job5    job6
```

Arrivals are irregular. Average rate = **λ** (lambda).

**Key result**: with Poisson rate λ, **inter-arrival times are
exponentially distributed with rate λ**.

So we sample one inter-arrival at a time:
```
sample x₁ ~ Exp(λ) → wait x₁ → arrival 1
sample x₂ ~ Exp(λ) → wait x₂ → arrival 2
```

### Concept: Exponential service times

Service time ~ Exp(μ):
- **μ (mu)** = average service completions per unit time
- Mean service time = 1/μ
- Individual values vary widely

### Why exponential? Memorylessness

If you've waited 10ms, expected remaining wait is still 1/λ.
The clock doesn't run down. This is what makes M/M/1 mathematically
tractable — you don't need to fully understand it.

### Stability: λ vs μ

| Scenario | Result |
|---|---|
| λ < μ | Queue stays small, system stable |
| λ = μ | Queue grows slowly, unbounded |
| λ > μ | Queue blows up, unstable |

**ρ = λ/μ** = utilization. Stability requires ρ < 1.

### Connection to PA1 experiments

| (μ, λ) | ρ | Behavior |
|---|---|---|
| (5, 3) | 0.60 | Modest queue |
| (3, 5) | 1.67 | **Unstable!** |
| (50, 30) | 0.60 | Modest queue |
| (50, 35) | 0.70 | Moderate queue |
| (50, 40) | 0.80 | Larger queue |
| (50, 45) | 0.90 | Very busy |
| (50, 48) | 0.96 | Critical — bounded only |

Progression is intentional: queue grows as ρ → 1.

### Concept: Sampling exponential numbers in C

Use **inverse-transform**:
1. Sample uniform u in [0, 1)
2. Return -ln(1 - u) / λ

The spec gives us:
```c
#include <stdlib.h>
#include <math.h>

double randexp(double lambda) {
    double u = rand() / ((double)RAND_MAX + 1.0);
    return -log(1.0 - u) / lambda;
}
```

Line by line:
- `(double)RAND_MAX + 1.0` ensures u is in [0, 1) — never exactly 1
- Why? Because `log(1-1) = log(0) = -∞` would crash
- `log()` in C `<math.h>` is **natural log** (ln), not log base 10

### Critical: order of rand() calls

For each job: x first (inter-arrival), then y (length):

```c
for (i = 0; i < num_jobs; i++) {
    double x = randexp(lambda);   // 1st rand() this iter
    /* sleep */
    double y = randexp(mu);       // 2nd rand() this iter
    /* send, log */
}
```

**Any extra rand() call shifts the sequence** — breaks reproducibility.
Grader can run with a known seed and compare.

### Unit conversion: ms → ns

> *Spec: "x and y… in milliseconds." "Sleep for 10⁶ · x nanoseconds."*

- x is in milliseconds
- 1 ms = 10⁶ ns
- Sleep `floor(10⁶ · x)` ns; same for y → wire job_length

---

## Step 4: Writing client.c — Skeleton

### Concept: The shape of every C program

```c
/* 1. Header includes */
#include <stdio.h>

/* 2. Helper function definitions */
double helper(double x) { ... }

/* 3. main() — entry point */
int main(int argc, char *argv[]) {
    /* program logic */
    return 0;  /* 0 = success, non-zero = error */
}
```

### Concept: main()'s arguments

`int main(int argc, char *argv[])`:
- `argc` = arg count (including program name)
- `argv` = arg vector (array of strings)

Example: `./client 127.0.0.1 9000 128 211 50.0 20.0`
- `argc = 7`
- `argv[0] = "./client"`, `argv[1] = "127.0.0.1"`, ...

### Concept: Header files for client.c

| Header | Provides | Used for |
|---|---|---|
| `<stdio.h>` | `printf`, `fprintf`, `perror` | stdout/stderr |
| `<stdlib.h>` | `strtol`, `srand`, `exit` | parsing, RNG |
| `<string.h>` | `memcpy`, `memset` | message build |
| `<unistd.h>` | `getpid`, `close` | PID, close |
| `<math.h>` | `log`, `floor` | randexp |
| `<time.h>` | `nanosleep`, `struct timespec` | sleep |
| `<sys/socket.h>` | `socket`, `sendto`, `AF_INET` | sockets |
| `<netinet/in.h>` | `struct sockaddr_in`, `htons` | addr + byte order |
| `<arpa/inet.h>` | `inet_pton` | parse IP |
| `<stdint.h>` | `uint32_t`, `uint16_t` | wire format types |

### Concept: POSIX feature-test macro

Some functions like `nanosleep` are POSIX, not pure ISO C. Under
`-std=c11 -Wpedantic`, they're hidden by default. Expose with:

```c
#define _POSIX_C_SOURCE 200809L   /* must come BEFORE any #include */
```

Without it: "implicit declaration" warnings.

### Coding conventions

- `static` before a function = "private to this file." Good for helpers.
- `(void)argc; (void)argv;` = explicit "unused for now" — silences
  `-Wunused-parameter`. Remove once you use them.

### Pattern

Write a clean skeleton with TODO comments, verify it compiles, then
fill in TODOs without breaking the build.

---

## Step 5: Argument Parsing in client.c

### Concept: Why not atoi() / atof()?

```c
int n = atoi("abc");   // returns 0 — no error reported!
```

These silently return 0 on garbage. Spec requires proper error handling.
Use `strtol` / `strtod` instead.

### Concept: strtol with endptr

```c
long strtol(const char *str, char **endptr, int base);
```

After the call:
- If parse consumed entire string: `*endptr` points to `'\0'`
- If garbage in middle: `*endptr` points to first bad char

Idiom:
```c
char *end;
long n = strtol(argv[1], &end, 10);
if (*end != '\0') { /* bad input */ }
```

`strtod` works the same for `double` (no `base` arg).

### Concept: inet_pton — parse IP

```c
int inet_pton(int family, const char *src, void *dst);
```

`AF_INET` for IPv4. Returns 1 on success, 0 if invalid, -1 on error.
Name = "**p**resentation **to** **n**etwork."

### Concept: Error handling pattern

> *Spec Section 2.3: "All errors should be logged properly to stderr
> (e.g., using perror), and exited with a non-zero error code."*

Two ways to write to stderr:

```c
/* For syscall failures: */
if (socket(...) < 0) {
    perror("socket");          /* prints: socket: Permission denied */
    exit(EXIT_FAILURE);
}

/* For our own errors: */
fprintf(stderr, "Usage: %s ...\n", argv[0]);
exit(EXIT_FAILURE);
```

`EXIT_FAILURE` is from `<stdlib.h>`, typically value 1.

### Concept: zero out sockaddr_in before use

```c
struct sockaddr_in dest;
memset(&dest, 0, sizeof(dest));
```

**Mandatory**, not optional. The struct has internal padding (`sin_zero`)
that some systems require to be zero. Forgetting this is a classic bug.

### Concept: htons for the port

```c
dest.sin_port = htons((uint16_t)port);
```

Port numbers in `sockaddr_in` MUST be in network byte order.
`htons` = "**h**ost **to** **n**etwork **s**hort."

### Validation rules in PA1

- port: parse + range check `[0, 65535]`
- num_jobs: parse + ≥ 0
- seed: parse only (any int)
- lambda, mu: parse + > 0 (rates positive, avoid div-by-zero)

---

## Step 6: Seed RNG and Create UDP Socket

### Concept: What srand() does

C's `rand()` is **pseudo-random** — deterministic sequence based on
internal state. `srand(seed)` initializes that state.

```c
srand(42);
int a = rand();   // always the same value with seed 42
int b = rand();
```

Why this matters: the grader can run with seed 211 and check our TSV
matches the reference exactly.

> *Spec Section 2.1: "the client initializes the seed using srand()."*

**Critical**: call `srand()` **once**, before any `rand()`.
Calling it inside the loop would reset the sequence each iteration.

### Concept: What socket() does

```c
int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
```

The OS:
1. Allocates a socket structure in kernel memory
2. Adds it to your process's file descriptor table
3. Returns the file descriptor number

Returns -1 on failure, with reason in `errno`.

### Why client doesn't bind()

> *Spec Section 2.2: "the client does not need to connect(), and
> instead calls sendto()."*

- `bind()` claims a specific local port for incoming traffic.
- The client only sends — doesn't need to be findable.
- The OS auto-assigns it some random ephemeral port for the source
  address when it first calls `sendto()`.
- The server sees that port in `recvfrom()` and uses it for logging.

### Always close what you open

```c
close(sockfd);
```

Spec requires (Section 2.3): "all sockets should be closed."
Leaks = bug.

### Cast: long → unsigned int for srand

```c
srand((unsigned int)seed);
```

`seed` is `long` from `strtol`; `srand` wants `unsigned int`.

---

## Step 7: Main Loop — Byte Order, Sleeping, and Sending

### Concept: Endianness

How multi-byte integers live in memory.

**Little-endian** (most desktops): least significant byte first.
**Big-endian** (some embedded): most significant first.

Storing `0x12345678`:

```
                   address →  0    1    2    3
Little-endian:               [78] [56] [34] [12]
Big-endian:                  [12] [34] [56] [78]
```

The number is the same; the byte layout differs.

### Why this matters for networking

If a little-endian client sends `0x12345678` raw to a big-endian
server, the server reads `0x78563412`. Wrong number.

### Network byte order = big-endian

Internet standard. Multi-byte fields on the wire MUST be big-endian.

| Function | Direction | Size |
|---|---|---|
| `htonl(x)` | Host → Network | 32-bit |
| `htons(x)` | Host → Network | 16-bit |
| `ntohl(x)` | Network → Host | 32-bit |
| `ntohs(x)` | Network → Host | 16-bit |

On little-endian, these swap bytes. On big-endian, no-op.
**Always call them** — the function handles the platform.

> *Spec Section 2.3: "You may want to use standard conversion functions
> such as ntohl()."*

### The 10-byte wire format for PA1

> *Spec 2.1: "Client ID (32 bits)... Job index (16 bits)... Job length
> in nanoseconds (32 bits): this is 10⁶ · y."*

Total: 32 + 16 + 32 = 80 bits = **10 bytes**.

```
Byte:    0      1      2      3      4      5      6      7      8      9
       ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
       │       client_id (32 bits)   │  index(16) │     job_length (32 bits)  │
       └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

#### What each field means

| Field | Identifies | Why server needs it |
|---|---|---|
| **Client ID** (32b) | Who sent it? | Multiple clients can run concurrently. PID is auto-unique per process. |
| **Job index** (16b) | Which job from that client? | Per-client counter starting at 0. Together with Client ID, uniquely IDs every job. |
| **Job length** (32b) | How long should server "work"? | Server's worker `nanosleep`s for this many ns to simulate processing. |

#### Why these sizes?

- 32-bit client_id: PIDs can reach ~4M; 32 bits safe
- 16-bit job_index: max 4000 in experiments; 16 bits = 64K headroom
- 32-bit job_length: ns counts up to ~4.3 sec, plenty

#### Why not just send a struct?

Tempting but dangerous:
```c
struct job_msg {
    uint32_t client_id;
    uint16_t job_index;
    uint32_t job_length;
};
sendto(sock, &msg, sizeof(msg), ...);
```

Two problems:
1. **Padding**: compiler may add hidden bytes between fields → could be
   12 bytes, not 10. Different platforms pad differently.
2. **Endianness**: still need conversion per field.

Solution: **manual serialization** with `memcpy` + `htonl`/`htons`.
Guarantees exactly 10 bytes, fixed layout, regardless of platform.

```c
uint8_t msg[10];
uint32_t net_id  = htonl(client_id);
uint16_t net_idx = htons(job_index);
uint32_t net_len = htonl(job_length_ns);
memcpy(msg + 0, &net_id,  4);
memcpy(msg + 4, &net_idx, 2);
memcpy(msg + 6, &net_len, 4);
```

Why `memcpy` and not casting? **Alignment**. Writing a `uint32_t*` to
an arbitrary byte offset is undefined behavior on some platforms.
`memcpy` is always safe.

### Concept: nanosleep + struct timespec

```c
struct timespec {
    time_t tv_sec;    // whole seconds
    long   tv_nsec;   // nanoseconds [0, 999999999]
};
```

`tv_nsec` is the **fractional** part — must be < 10⁹.
For N nanoseconds total:

```c
struct timespec ts;
ts.tv_sec  = N / 1000000000L;
ts.tv_nsec = N % 1000000000L;
nanosleep(&ts, NULL);    /* NULL = don't care about leftover on signal */
```

### Concept: sendto for UDP

```c
ssize_t sendto(int sockfd, const void *buf, size_t len, int flags,
               const struct sockaddr *dest_addr, socklen_t addrlen);
```

- `flags` — 0 normally
- `dest_addr` — pointer to `sockaddr_in`, cast to generic `sockaddr*`
- `addrlen` — `sizeof(struct sockaddr_in)`

Returns bytes sent (== `len`) or -1 on error.

The cast `(struct sockaddr *)&dest` is standard idiom — `sockaddr_in`
(IPv4), `sockaddr_in6` (IPv6), etc. share a common header, and the
API uses generic `sockaddr` to be protocol-neutral.

### The TSV log format

> *Spec: `printf("%08x:%04x\t%d:%d\t%d\t%d\n", ip, port, id, index, floor_x, floor_y);`*

`ip` and `port` = the **destination** server's address. We have them
in `dest` in network byte order. Convert before printing in hex:

```c
uint32_t ip_host   = ntohl(dest.sin_addr.s_addr);
uint16_t port_host = ntohs(dest.sin_port);
```

`%08x` = unsigned hex, at least 8 chars, zero-padded.
- `127.0.0.1` = `0x7F000001` → `7f000001`
- `9000` = `0x2328` → `2328`

`floor_x` and `floor_y` are the **nanosecond values**:
- `floor_x = (int)floor(1e6 * x)` (same value used in nanosleep)
- `floor_y = (int)floor(1e6 * y)` (same value sent on wire)

### Connection to the simulation

```
Client                                           Server
──────                                           ──────
sample inter-arrival time x                      
sleep x ms                                       
sample job length y                              
build msg: [pid][i][1e6·y]  ──UDP─►  recvfrom: get [pid][i][len]
                                     enqueue {pid, i, len, arrival_time}
                                     worker dequeues, sleeps `len` ns
                                     records departure_time, logs
```

---

## Step 8: Moving to server.c — Threading Foundation

### Concept: Threads vs Processes

A **process** is a self-contained running program with its own memory.
A **thread** is a sequence of instructions being executed by the CPU.

Every process starts with one thread (the *main thread*) and can
spawn more.

```
   ┌────── Process: ./server (PID 9876) ──────┐
   │   Memory shared by all threads:          │
   │   [ heap ]  [ globals ]  [ code ]        │
   │                                          │
   │   Thread 1 (main / acceptor)             │
   │     ├─ stack (private)                   │
   │     └─ instruction pointer               │
   │                                          │
   │   Thread 2 (worker)                      │
   │     ├─ stack (private)                   │
   │     └─ instruction pointer               │
   └──────────────────────────────────────────┘
```

- Threads share heap, globals, code.
- Each has its own stack (locals are private).
- Run concurrently. **OS scheduler decides ordering — unpredictable.**

### pthread API

```c
pthread_t worker;
pthread_create(&worker, NULL, worker_function, arg_to_pass);
/* main continues; worker runs concurrently */
pthread_join(worker, NULL);   /* block until worker exits */
```

- `pthread_create(thread, attrs, func, arg)` — spawn; immediately
  calls `func(arg)`. `attrs = NULL` → defaults.
- `pthread_join(thread, ret)` — block until that thread exits.

### Race conditions

Two threads doing `count++` on shared memory can lose updates.
`count++` is 3 CPU steps (read, add, write). Interleaved:

```
  Time →
  Thread A:   read(0)        +1 (=1)        write(1)
  Thread B:        read(0)         +1 (=1)         write(1)
                                                       ▲
                                          count is 1, not 2 — lost update!
```

For PA1: unprotected concurrent enqueue/dequeue corrupts the linked list.

### Mutex (mutual exclusion)

A lock only one thread can hold at a time. Protects critical sections.

```c
pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;

pthread_mutex_lock(&lock);   /* wait, then take */
/* critical section: modify shared queue */
pthread_mutex_unlock(&lock); /* release */
```

If A holds, B blocks until A unlocks. Then B proceeds.

**Rule**: every read/write of shared mutable state inside `lock`/`unlock`.

### Condition variables

Mutex alone isn't enough. Bad worker:

```c
/* Busy-wait — burns 100% CPU */
while (1) {
    pthread_mutex_lock(&lock);
    if (queue_empty()) { pthread_mutex_unlock(&lock); continue; }
    /* ... */
}
```

A **condition variable** lets a thread sleep until something happens.

```c
pthread_cond_t not_empty = PTHREAD_COND_INITIALIZER;
```

Two key ops:

- `pthread_cond_wait(&cond, &lock)`:
  1. Atomically: release lock + sleep
  2. On signal: wake up, re-acquire lock, return

- `pthread_cond_signal(&cond)`: wake one waiter
- `pthread_cond_broadcast(&cond)`: wake all waiters

### Producer/consumer pattern

```c
/* Worker (consumer) */
pthread_mutex_lock(&lock);
while (queue_empty() && !done) {              /* ALWAYS while, not if */
    pthread_cond_wait(&not_empty, &lock);
}
if (queue_empty() && done) {
    pthread_mutex_unlock(&lock);
    return;
}
job = dequeue();
pthread_mutex_unlock(&lock);
process(job);
```

```c
/* Acceptor (producer) */
pthread_mutex_lock(&lock);
enqueue(job);
pthread_cond_signal(&not_empty);
pthread_mutex_unlock(&lock);
```

### Why `while` and not `if`?

1. **Spurious wakeups**: `pthread_cond_wait` can return without a signal.
2. **Multiple waiters**: another thread might have grabbed the job first.

Universal idiom: `while (!predicate) cond_wait(...)`.

### The big picture

```
        ┌────── shared queue (mutex-protected) ──────┐
        ▼                                            │
   ┌──────────┐                              ┌──────────┐
   │ Acceptor │ ──enqueue──► [a][b][c] ──► dequeue ──► │  Worker  │
   │(producer)│              FIFO                     │(consumer)│
   └──────────┘                                       └──────────┘
        ▲                                                    │
        │ recvfrom packets                                   │ nanosleep + log
```

> *Spec Section 2.2: "Since both threads access the queue, some
> synchronization, such as a mutex is required."*

---

## Step 9: Remaining Server Concepts

### 9a. STAILQ from `<sys/queue.h>`

C has no built-in linked list. `<sys/queue.h>` provides macros that
generate a typed list at compile time. **STAILQ** = Singly-linked
TAIL Queue.

```c
#include <sys/queue.h>

/* 1. Element type — add STAILQ_ENTRY */
struct job {
    uint32_t client_id;
    /* ... */
    STAILQ_ENTRY(job) entries;   /* hidden "next" */
};

/* 2. Head type */
STAILQ_HEAD(job_head, job);

/* 3. Instance + init */
struct job_head queue_head;
STAILQ_INIT(&queue_head);
```

Operations:
```c
STAILQ_INSERT_TAIL(&queue_head, j, entries);   /* O(1) enqueue */
struct job *first = STAILQ_FIRST(&queue_head);
STAILQ_REMOVE_HEAD(&queue_head, entries);      /* O(1) dequeue */
int empty = STAILQ_EMPTY(&queue_head);

struct job *j;
STAILQ_FOREACH(j, &queue_head, entries) { /* visit j */ }
```

### 9b. malloc and free — heap memory

Stack memory dies when the function returns. Job objects must outlive
the receive call (queue waiting + processing in another thread).
Use heap.

```c
struct job *j = malloc(sizeof(*j));
if (j == NULL) { perror("malloc"); exit(EXIT_FAILURE); }
/* fill j, enqueue */

/* later, after processing: */
free(j);
```

Rules:
- Always check `malloc` for NULL
- Each malloc balanced by exactly one free
- Never dereference a freed pointer (use-after-free)

PA1 ownership flow:
- Acceptor mallocs per datagram
- Drop case: free immediately
- Enqueue case: ownership transfers to queue
- Worker dequeues, processes, frees

### 9c. clock_gettime(CLOCK_MONOTONIC)

> *Spec 2.2: "use clock_gettime() with CLOCK_MONOTONIC.
> Do not use other functions/syscalls to get the time."*

Why monotonic?

| Clock | Behavior |
|---|---|
| CLOCK_REALTIME | Wall clock; jumps with NTP. Bad for intervals. |
| CLOCK_MONOTONIC | Monotonic since boot. Perfect for intervals. |

```c
struct timespec t;
clock_gettime(CLOCK_MONOTONIC, &t);
long ns = t.tv_sec * 1000000000L + t.tv_nsec;   /* use long, not int */
```

PA1: capture `t0` at startup; each timestamp = `(now - t0)` in ns.

### 9d. recvfrom — receiving and decoding

Mirror of `sendto`:

```c
ssize_t recvfrom(int sockfd, void *buf, size_t len, int flags,
                 struct sockaddr *src_addr, socklen_t *addrlen);
```

- `src_addr` (out): filled with sender's address
- `addrlen` (in/out): start as `sizeof(sockaddr_in)`, kernel may shrink

`recvfrom` blocks until a datagram arrives.

```c
uint8_t buf[10];
struct sockaddr_in src;
socklen_t srclen = sizeof(src);
ssize_t n = recvfrom(sockfd, buf, sizeof(buf), 0,
                     (struct sockaddr *)&src, &srclen);
if (n != 10) { perror("recvfrom"); /* error */ }

uint32_t client_id, job_length;
uint16_t job_index;
memcpy(&client_id,  buf + 0, 4);  client_id  = ntohl(client_id);
memcpy(&job_index,  buf + 4, 2);  job_index  = ntohs(job_index);
memcpy(&job_length, buf + 6, 4);  job_length = ntohl(job_length);
```

Then `src.sin_addr.s_addr` and `src.sin_port` (network byte order)
hold the client's address — convert with `ntohl`/`ntohs` for logging.

### 9e. Where does num_jobs come from?

`num_jobs` is **NOT in the wire format**. Client never tells server.

> *Spec invocation:*
> *Client: `client ip port num_jobs seed lambda mu`*
> *Server: `server port num_jobs q_size`*

Both programs get it as a command-line arg, set independently by
the operator.

**Examples:**
- Single client: `./server 9000 1000 100 &; ./client ... 1000 ...`
- Two clients (Experiment 2): `./server 9000 4000 100 &; ./client ... 2000 &; ./client ... 2000 &`

### 9f. Drops still count

> *Spec 2.2: "dropped jobs are counted as jobs accepted by the server,
> even though they do not enter the queue."*

```c
long received = 0;
while (received < num_jobs) {
    recvfrom(...);
    received++;       /* ALWAYS — even on drop */
    /* enqueue or drop */
}
```

If drops didn't count, bounded-queue experiments would hang.

Drop count for analysis = `client_jobs - server_log_lines`.

### 9g. Shutdown protocol

When acceptor reaches num_jobs, signal worker to drain and exit.

```c
/* Acceptor */
pthread_mutex_lock(&lock);
done = 1;
pthread_cond_signal(&not_empty);
pthread_mutex_unlock(&lock);
pthread_join(worker_thread, NULL);
```

```c
/* Worker */
while (1) {
    pthread_mutex_lock(&lock);
    while (queue_empty() && !done) {
        pthread_cond_wait(&not_empty, &lock);
    }
    if (queue_empty() && done) {       /* drain-then-exit */
        pthread_mutex_unlock(&lock);
        return NULL;
    }
    struct job *j = dequeue();
    pthread_mutex_unlock(&lock);
    /* sleep job->len */
    /* timestamp departure */
    /* lock, read q_num/q_time, unlock */
    /* printf */
    /* lock, decrement counters, unlock */
    free(j);
}
```

Exit condition: **queue empty AND done**, never just `done`.

### 9h. Order of counter updates (per lecturer clarification)

The just-finished job is **included** in its own log line. Worker order:

1. Dequeue (job: waiting → executing; still in system)
2. Sleep `job_length`
3. Read q_num, q_time — both still include this job
4. Print log line
5. Decrement `jobs_in_system`, subtract length
6. `free` the job

**Order matters**: read counters BEFORE decrementing.

---

## Step 10: Writing server.c — Skeleton

### Concept: struct job

One per received datagram. Stores everything needed to log + sleep:

```c
struct job {
    uint32_t client_ip_net;     /* network byte order */
    uint16_t client_port_net;   /* network byte order */
    uint32_t client_id;         /* host order */
    uint16_t job_index;         /* host order */
    uint32_t job_length_ns;     /* host order */
    long     arrival_ns;        /* ns since t0 */
    STAILQ_ENTRY(job) entries;
};
```

### Concept: queue_t — count vs jobs_in_system

Two separate counters because they answer different questions.

| Field | Used for |
|---|---|
| `count` | Jobs in FIFO (waiting only) — for drop policy |
| `jobs_in_system` | Queue + executing — for q_num column |
| `total_length_in_system` | Sum of in-system lengths — for q_time |
| `capacity` | q_size from cmd-line |
| `done` | Acceptor sets when num_jobs received |
| `mutex`, `not_empty` | Synchronization |

When the worker dequeues: `count--` (left FIFO), but `jobs_in_system`
unchanged (still being processed). After logging: `jobs_in_system--`.

### Concept: server_ctx

Bundles `queue_t *` + `t0_ns` so we can pass one pointer to the worker
via `pthread_create`.

```c
typedef struct {
    queue_t *queue;
    long     t0_ns;
} server_ctx;
```

### Concept: now_ns helper

Wraps `clock_gettime(CLOCK_MONOTONIC, ...)` and returns one big ns int.

```c
static long now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000000000L + ts.tv_nsec;
}
```

### Concept: Forward declaration

`main` references `worker_thread` for `pthread_create`. The function
body comes after `main`. Need a forward declaration:

```c
static void *worker_thread(void *arg);

int main(...) { /* uses &worker_thread */ }

static void *worker_thread(void *arg) { /* body */ }
```

---

## Step 11: Server Argument Parsing

Same pattern as client. 3 args:

| argv | Name | Constraints |
|---|---|---|
| `argv[1]` | `port` | 0 ≤ port ≤ 65535 |
| `argv[2]` | `num_jobs` | > 0 |
| `argv[3]` | `q_size` | > 0 (large for "unbounded") |

> *Spec 2.2: `server port num_jobs q_size`*

The "unbounded queue" = q_size > num_jobs. No special code path needed.

---

## Step 12: Initialize the Queue

### Concept: Two ways to initialize a pthread mutex

**Static initializer** (only at declaration of global/static var):
```c
pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t  cond = PTHREAD_COND_INITIALIZER;
```

**Runtime initialization** (works anywhere — including struct fields):
```c
pthread_mutex_init(&lock, NULL);   /* NULL = default attributes */
pthread_cond_init (&cond, NULL);
```

PA1: mutex/cond inside `queue_t`, a stack-local struct → use runtime.

### Default attributes (the NULL second arg)

`NULL` = "use defaults": non-recursive, no priority inheritance,
process-private. What we want.

### Init/destroy pairing

Every successful init must be balanced by destroy or we leak kernel
resources (Valgrind catches it).

```c
pthread_mutex_init(&m, NULL);
/* use */
pthread_mutex_destroy(&m);
```

### Cleanup order on partial init failure

If mutex init succeeded but cond init failed, **destroy the mutex first**:

```c
if (pthread_mutex_init(&q.mutex, NULL) != 0) { /* error */ return; }
if (pthread_cond_init(&q.not_empty, NULL) != 0) {
    perror("pthread_cond_init");
    pthread_mutex_destroy(&q.mutex);   /* unwind previous init */
    return;
}
```

C rhythm: every successful resource acquire has a release partner.
On error, unwind in reverse.

### Stack-local pthread state is fine

Our `queue_t queue;` is on `main`'s stack. Worker holds a pointer.
**Safe because main does pthread_join before returning** — the queue
outlives the worker.

If main returned without joining, the queue would be destroyed
underneath the worker → undefined behavior. The join is critical.

### No special "unbounded" code path

Unbounded = pass `q_size > num_jobs`. We just store and check it.
For unbounded experiments, the drop branch never fires.

---

## Step 13: Server Socket — bind, INADDR_ANY, SO_REUSEADDR

### Concept: Why server needs bind()

When the OS receives a UDP datagram, it looks at the destination port
and finds which socket bound to it.

- **Client**: doesn't bind. OS picks ephemeral port automatically.
- **Server**: must bind to a fixed port clients can target.

> *Spec 2.2: "the server must still bind() to its address"*

### bind() syntax

```c
int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen);
```

Same `struct sockaddr_in`, but filled with **our own** listen address:

```c
struct sockaddr_in addr;
memset(&addr, 0, sizeof(addr));
addr.sin_family      = AF_INET;
addr.sin_port        = htons((uint16_t)port);
addr.sin_addr.s_addr = htonl(INADDR_ANY);
```

### INADDR_ANY = all interfaces

`INADDR_ANY` is `0.0.0.0` — "any local address." A machine has
multiple interfaces (ethernet, wi-fi, loopback). `INADDR_ANY` accepts
from all. (Could bind to a specific IP to restrict.)

### SO_REUSEADDR — quality of life

Quickly restart the server and you might see:
```
bind: Address already in use
```

The OS keeps the previous socket in TIME_WAIT briefly. Setting
`SO_REUSEADDR` lets you bind anyway:

```c
int yes = 1;
setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
```

Not strictly required by spec; very useful while iterating.

### Error-unwind chain grows

By socket + setsockopt + bind, an error has a lot to unwind:

```c
int sockfd = socket(...);
if (sockfd < 0) { perror; cleanup_pthreads; return; }

if (setsockopt(...) < 0) {
    perror; close(sockfd); cleanup_pthreads; return;
}
if (bind(...) < 0) {
    perror; close(sockfd); cleanup_pthreads; return;
}
```

Each new acquisition adds a line to later operations' cleanup.
Some C codebases use `goto cleanup` to deduplicate; we keep it
explicit for clarity.

---

## Step 14: Record t0 and Spawn the Worker Thread

### Concept: pthread_create signature

```c
int pthread_create(pthread_t *thread,
                   const pthread_attr_t *attr,
                   void *(*start_routine)(void *),
                   void *arg);
```

The 3rd argument `void *(*start_routine)(void *)` is a **function pointer
type**, read inside-out:
- `(*start_routine)` — pointer to a function...
- `(void *)` — that takes a single `void *`...
- `void *` — and returns a `void *`.

So the worker function MUST have exactly this signature:
```c
void *worker_thread(void *arg) { ... }
```

Why `void *`? It's C's "any pointer" type. `pthread_create` doesn't know
what data your thread needs — you cast a pointer to anything → `void *`
on the way in, and cast back inside the worker.

### Concept: pthread_* error reporting differs

`pthread_*` functions **return error codes directly** — they do NOT set
`errno`. So `perror` doesn't work for them. Use `strerror`:

```c
int rc = pthread_create(...);
if (rc != 0) {
    fprintf(stderr, "pthread_create: %s\n", strerror(rc));
}
```

Returns 0 on success.

### Concept: Passing data via void *

Bundle shared state in a struct, pass a pointer:

```c
server_ctx ctx = { .queue = &queue, .t0_ns = t0_ns };
pthread_create(&worker, NULL, worker_thread, &ctx);
```

`{ .field = value }` is **C99 designated initializer syntax** — explicit,
readable, avoids ordering bugs of `{ &queue, t0_ns }`.

Inside the worker:
```c
static void *worker_thread(void *arg) {
    server_ctx *ctx = (server_ctx *)arg;   /* cast back */
    queue_t *q = ctx->queue;
    long t0 = ctx->t0_ns;
    /* ... */
}
```

**Lifetime warning**: `ctx` is on `main`'s stack. The worker reads through
this pointer for its entire life → `main` MUST not return until the
worker is joined. We always pthread_join before returning.

### Concept: pthread_join

```c
int pthread_join(pthread_t thread, void **retval);
```

Blocks until `thread` exits. If you care about the thread's return value,
pass `void **retval`. We don't, so pass `NULL`:

```c
pthread_join(worker, NULL);
```

After `pthread_join` returns, the thread's resources are cleaned up.
**Every thread must be joined (or detached)** — otherwise zombie state
leaks.

### Why record t0 just before pthread_create?

`t0` is our "server start" reference. Every arrival/departure timestamp
in the log = `now - t0`. Record it just before the worker starts so:
- Both threads see the same `t0`
- It's as close as possible to when the first packet might arrive

### Temporary join placement

We're spawning a thread but the worker function is still a stub —
returns immediately. To avoid leaving a zombie, we add `pthread_join`
right before cleanup:

```c
pthread_create(&worker, NULL, worker_thread, &ctx);

/* TODO 5: acceptor loop */
/* TODO 6: shutdown handshake (set done flag, signal worker) */

pthread_join(worker, NULL);   /* will move into TODO 6 later */
close(sockfd);
/* destroy mutex/cond */
```

Once we implement TODO 5 and TODO 6, this join moves into the proper
shutdown sequence.

---

## Step 15: The Acceptor Loop

### Concept: Timestamp arrival IMMEDIATELY

Arrival timestamp must reflect when the packet entered our process,
not when we got around to processing it.

```c
ssize_t n = recvfrom(...);
long arrival_ns = now_ns() - t0_ns;   /* FIRST thing after recvfrom */
/* then check errors, decode, etc. */
```

Decode-then-timestamp would add small bias to every arrival. Easy to
do right.

### Concept: Decoding 10-byte wire format

Mirror of the client encode:

```c
uint8_t buf[10];
recvfrom(sockfd, buf, sizeof(buf), 0, ...);

uint32_t client_id, job_length_ns;
uint16_t job_index;
memcpy(&client_id,     buf + 0, 4);  client_id     = ntohl(client_id);
memcpy(&job_index,     buf + 4, 2);  job_index     = ntohs(job_index);
memcpy(&job_length_ns, buf + 6, 4);  job_length_ns = ntohl(job_length_ns);
```

Same offsets, same sizes, opposite direction (`ntohl`/`ntohs`).

### Concept: Sender address — keep in network order

`recvfrom` fills `src` with the sender's IP+port in network byte order.
We store them as-is in the `struct job`, only converting (`ntohl`/`ntohs`)
when printing the log line. Avoids redundant conversions.

```c
j->client_ip_net   = src.sin_addr.s_addr;
j->client_port_net = src.sin_port;
```

### Concept: Lock-check-act for enqueue/drop

```c
pthread_mutex_lock(&queue.mutex);
if (queue.count >= queue.capacity) {
    pthread_mutex_unlock(&queue.mutex);
    free(j);
} else {
    STAILQ_INSERT_TAIL(&queue.head, j, entries);
    queue.count++;
    queue.jobs_in_system++;
    queue.total_length_in_system += j->job_length_ns;
    pthread_cond_signal(&queue.not_empty);
    pthread_mutex_unlock(&queue.mutex);
}
```

Three things to notice:

1. **Capacity check inside the lock** — otherwise `count` could be stale.
2. **Three counters updated atomically** — `count`, `jobs_in_system`,
   `total_length_in_system` must stay consistent under one lock.
3. **Signal inside the lock is fine** — POSIX allows it. Worker will
   wake but immediately re-acquire the lock anyway.

### Concept: The receive-count invariant

```c
long received = 0;
while (received < num_jobs) {
    /* recvfrom, decode, enqueue OR drop */
    received++;        /* always — even on drop */
}
```

Drops still increment `received`. Without this, bounded-queue experiments
would hang waiting for arrivals the client already sent.

### Sanity behavior of the current code

Running `./server 9000 5 100` now:
1. Bind to 9000
2. Spawn worker (stub returns immediately)
3. Acceptor recvfroms 5 datagrams, enqueues each
4. Loop ends
5. pthread_join returns immediately (worker already done)
6. Cleanup

But: the queue still holds 5 unprocessed jobs → memory leak. The real
worker will dequeue them. Until then, 5 jobs leak per run.

---

## Step 16: The Worker Thread Body

### Concept: Casting the void * arg back

The thread starts with `arg : void *`, but we know it's really a
`server_ctx *`. Cast and grab handles for the loop:

```c
server_ctx *ctx = (server_ctx *)arg;
queue_t *q = ctx->queue;
long t0 = ctx->t0_ns;
```

### Concept: Wait-and-exit gate

```c
pthread_mutex_lock(&q->mutex);
while (STAILQ_EMPTY(&q->head) && !q->done) {
    pthread_cond_wait(&q->not_empty, &q->mutex);
}
if (STAILQ_EMPTY(&q->head) && q->done) {
    pthread_mutex_unlock(&q->mutex);
    return NULL;
}
```

| Queue | done? | Action |
|---|---|---|
| Empty | No | Wait on cond |
| Empty | Yes | Exit thread |
| Non-empty | No | Dequeue |
| Non-empty | Yes | Dequeue (drain) |

`while`, not `if` — spurious wakeups + multiple waiters.

### Concept: Dequeue decrements only `count`

```c
struct job *j = STAILQ_FIRST(&q->head);
STAILQ_REMOVE_HEAD(&q->head, entries);
q->count--;
```

`jobs_in_system` and `total_length_in_system` stay unchanged. The job
left the FIFO but is still in the system (executing).

### Concept: Sleep outside the lock

```c
pthread_mutex_unlock(&q->mutex);

struct timespec ts;
ts.tv_sec  = j->job_length_ns / 1000000000L;
ts.tv_nsec = j->job_length_ns % 1000000000L;
nanosleep(&ts, NULL);

long departure_ns = now_ns() - t0;
```

Don't block the acceptor while we "process." Only the dequeue itself
needs the lock.

### Concept: Lock-snapshot-unlock for reading state

```c
pthread_mutex_lock(&q->mutex);
int  q_num  = q->jobs_in_system;
long q_time = q->total_length_in_system;
pthread_mutex_unlock(&q->mutex);

printf(...);    /* slow — outside the lock */
```

Read with the lock held; copy into local vars; release; print without
the lock. printf to stdout (especially redirected to a file) is slow —
holding the lock would needlessly stall the acceptor.

### Concept: Just-finished job is still counted

When we read `q_num` and `q_time`, we **haven't decremented yet** — so
both counters still include the just-finished job. This matches the
lecturer's clarification: J's log line includes J itself.

After printing, decrement and free:

```c
pthread_mutex_lock(&q->mutex);
q->jobs_in_system--;
q->total_length_in_system -= (long)j->job_length_ns;
pthread_mutex_unlock(&q->mutex);

free(j);
```

### Concept: Format string straight from spec

> *Spec 2.2: `printf("%08x:%04x\t%d:%d\t%ld\t%ld\t%d\t%ld\n", ip, port,
> job.id, job.index, arrival_time, departure_time, q_num, q_time);`*

```c
printf("%08x:%04x\t%d:%d\t%ld\t%ld\t%d\t%ld\n",
       (unsigned int)ntohl(j->client_ip_net),
       (unsigned int)ntohs(j->client_port_net),
       (int)j->client_id,
       (int)j->job_index,
       j->arrival_ns,
       departure_ns,
       q_num,
       q_time);
```

The casts:
- `(unsigned int)ntohl(...)` — `%08x` expects unsigned int
- `(unsigned int)ntohs(...)` — `%04x` expects unsigned int
- `(int)j->client_id` — `%d` expects int (client_id is uint32_t)
- `(int)j->job_index` — `%d` expects int (job_index is uint16_t)
- arrival_ns and departure_ns are already `long` for `%ld`
- q_num is `int`, q_time is `long` — match `%d` and `%ld`

### Important: deadlock without shutdown handshake

If the acceptor finishes its loop while the worker is in `cond_wait`,
the worker will sleep forever (queue empty, done still 0) and
`pthread_join` will hang.

This is why we need TODO 6 / Step 17: set `done = 1`, signal cond,
THEN join. Without it, the server hangs at the end.

---

## Step 17: The Shutdown Handshake

### Concept: The "lost wakeup" race

Naïve attempt:

```c
queue.done = 1;
pthread_cond_signal(&queue.not_empty);
pthread_join(worker, NULL);
```

Bug interleaving:
```
Worker                              Main
──────                              ────
lock mutex
check empty: TRUE
check done:  FALSE                  queue.done = 1;
                                    pthread_cond_signal(&...);  ← lost!
cond_wait(...)  ← sleeps, signal already happened
                                    pthread_join(worker)
                                    ↓ HANG forever
```

`pthread_cond_signal` only wakes a thread **currently** waiting.
If the worker hasn't entered `cond_wait` yet, the signal is lost.

This bug is called **lost wakeup** or **missed signal**.

### Concept: The fix — hold the mutex

```c
pthread_mutex_lock(&queue.mutex);
queue.done = 1;
pthread_cond_signal(&queue.not_empty);
pthread_mutex_unlock(&queue.mutex);
```

The worker holds the mutex while checking its predicate (`empty && !done`).
`cond_wait` is **atomic** — releases the mutex AND sleeps in one
indivisible step.

Two cases:

(a) Worker has already entered `cond_wait` → mutex was released atomically →
    we can acquire it → set done → signal wakes the worker.

(b) Worker hasn't entered `cond_wait` yet (still checking the predicate) →
    we can't acquire the mutex until it either enters cond_wait OR
    proceeds to dequeue. Either way, when the worker re-checks the
    predicate, it will see done = 1 and not wait.

The mutex+cond duo prevents missed wakeups **as long as you hold the
mutex when modifying the predicate's state**.

### Concept: Drain semantics

Setting `done = 1` doesn't tell the worker to stop immediately — it
says "no more jobs are coming." The worker still drains:

```c
while (1) {
    /* lock; while (empty && !done) cond_wait; */
    /* if (empty && done) return; */         ← only exit when EMPTY
    /* dequeue, process, repeat */
}
```

If there are 7 jobs queued when we set `done`, the worker processes
all 7 before exiting. `pthread_join` just waits.

> *Spec 2.2: "After receiving num_jobs jobs, the acceptor thread joins
> with the worker thread, waiting for it to finish processing pending
> jobs (if any), and then the process exits."*

### The pattern

```c
/* End of acceptor loop */

pthread_mutex_lock(&queue.mutex);
queue.done = 1;
pthread_cond_signal(&queue.not_empty);
pthread_mutex_unlock(&queue.mutex);

pthread_join(worker, NULL);

close(sockfd);
pthread_cond_destroy(&queue.not_empty);
pthread_mutex_destroy(&queue.mutex);
```

Order:
1. Lock
2. Set done
3. Signal
4. Unlock
5. Join (blocks until worker exits)
6. Close socket
7. Destroy cond, mutex (reverse order of init)

### When does cond_signal vs cond_broadcast matter?

We have **one worker** → `cond_signal` (wake one) is fine.
With multiple workers waiting, `cond_broadcast` would wake all.

PA1 only ever has one worker, so signal is correct.

---

## Step 18: q_num vs q_time vs Duration — What Each Measures

This is the most subtle part of the server output. Three distinct
quantities that all live near the log line and are easy to confuse.

### The three measurements

| Quantity | Meaning | What it tells you |
|---|---|---|
| `departure − arrival` | How long **this one job** spent in the system | Per-job duration (queue wait + service) |
| `q_num` (col 7) | Number of **jobs** in the system at log time | Snapshot of system load (count) |
| `q_time` (col 8) | Sum of **job lengths** of all jobs in the system at log time | Snapshot of remaining work |

`q_num` and `q_time` are about the **state of the whole system** at the
moment we log. `departure − arrival` is about **one specific job's journey**.

### Does q_num include the just-finished job?

**Yes.** Per the lecturer's clarification:

> *"The total number of jobs that are in the system, i.e., have already
> arrived and did not finish processing. The statistics to be printed
> should include the job that just finished execution."*

At the moment the worker prints J's log line, J is **counted** in q_num
and its length is **included** in q_time. That's why every line has
`q_num ≥ 1` — at minimum, the job being logged itself.

If we did NOT include the just-finished job, single-job moments would
show `q_num=0` and `q_time=0`, contradicting the spec.

### Is q_time = departure − arrival?

**No.** They measure different things and rarely match (except by
coincidence in trivial cases).

> *Spec Section 2.2: "total current demand: the sum of all lengths of
> jobs in the queue, including the job currently executing."*

`q_time` is a **snapshot of remaining work**. Imagine: "if no new jobs
arrived, how much total processing time would still need to happen?"

`departure − arrival` includes **wait time in the FIFO** that doesn't
appear in q_time at all.

### Mental picture

```
                          The system at log time of J
                          ─────────────────────────────
         (J just finished)              (other jobs still in queue)
              ↓                                    ↓
       ┌──────────────┐    ┌─────────┐ ┌─────────┐ ┌─────────┐
       │  J (len=ℓ_J) │    │ len=ℓ_a │ │ len=ℓ_b │ │ len=ℓ_c │
       └──────────────┘    └─────────┘ └─────────┘ └─────────┘

      q_num  = 4   (count of all boxes, including J)
      q_time = ℓ_J + ℓ_a + ℓ_b + ℓ_c
                  (sum of lengths of all boxes — including J)

      duration_J = J's departure − J's arrival
                   (a per-job time, not related to q_time)
```

### Verified with our smoke-test data (5-job run)

`server.tsv`:
```
7f000001:dd49	66024:0	376725000	376783000	3	63382
7f000001:dd49	66024:1	376731000	376809000	2	26204
7f000001:dd49	66024:2	376765000	376826000	1	10925
7f000001:dd49	66024:3	376844000	376895000	2	50763
7f000001:dd49	66024:4	376871000	376918000	1	14859
```

`client.tsv` (lengths in column 4):
```
job 0 length = 37178
job 1 length = 15279
job 2 length = 10925
job 3 length = 35904
job 4 length = 14859
```

Cross-checking q_time = sum of in-system lengths:

| Log line | q_num | q_time | Sum of lengths in system | Match? |
|---|---|---|---|---|
| job 0 | 3 | 63382 | 37178 + 15279 + 10925 | **63382** ✓ |
| job 1 | 2 | 26204 | 15279 + 10925 | **26204** ✓ |
| job 2 | 1 | 10925 | 10925 | **10925** ✓ |
| job 3 | 2 | 50763 | 35904 + 14859 | **50763** ✓ |
| job 4 | 1 | 14859 | 14859 | **14859** ✓ |

And duration ≠ q_time:

| Job | duration (departure − arrival) | q_time |
|---|---|---|
| 0 | 58000 ns | 63382 ns |
| 1 | 78000 ns | 26204 ns |
| 2 | 61000 ns | 10925 ns |
| 3 | 51000 ns | 50763 ns |
| 4 | 47000 ns | 14859 ns |

For job 2 (a "lonely" job): duration=61µs but its own length is only
~11µs — meaning ~50µs of that was **wait time** sitting in the FIFO
behind jobs 0 and 1. The wait time is NOT in q_time.

### Implementation invariant

The worker enforces this in code (Step 16):

1. Dequeue J. `count--`. **`jobs_in_system` unchanged** — J is still
   in the system, just executing now.
2. Sleep for `j->job_length_ns`.
3. Capture `departure_ns`.
4. Lock; **read** `jobs_in_system` and `total_length_in_system` →
   these still include J.
5. Unlock; `printf` the log line with those snapshots.
6. Lock; `jobs_in_system--`; `total_length_in_system -= j->len`.
7. Unlock; `free(j)`.

**Read counters BEFORE decrementing, log BEFORE decrementing** — so
J appears in its own log line.

---
