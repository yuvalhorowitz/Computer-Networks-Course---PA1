#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <time.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/queue.h>

/* A single job tracked in the system. Allocated by the acceptor on
 * recvfrom, freed by the worker after logging (or by acceptor on drop). */
struct job {
    uint32_t client_ip_net;     /* sender IP   — network byte order */
    uint16_t client_port_net;   /* sender port — network byte order */
    uint32_t client_id;         /* decoded from wire (host order) */
    uint16_t job_index;         /* decoded from wire */
    uint32_t job_length_ns;     /* decoded from wire */
    long     arrival_ns;        /* ns since server start (t0) */
    STAILQ_ENTRY(job) entries;  /* hidden "next" pointer for STAILQ */
};

STAILQ_HEAD(job_head, job);

/* Synchronized FIFO queue shared between the acceptor and worker threads.
 * All fields below are protected by `mutex`. */
typedef struct {
    struct job_head head;            /* the FIFO */
    int  count;                      /* jobs in FIFO (waiting only) */
    int  jobs_in_system;             /* queue + executing — used for q_num */
    long total_length_in_system;     /* sum of lengths in system — q_time */
    int  capacity;                   /* q_size from cmd-line; max FIFO size */
    int  done;                       /* acceptor sets when num_jobs received */
    pthread_mutex_t mutex;
    pthread_cond_t  not_empty;
} queue_t;

/* Context bundle passed to the worker thread. */
typedef struct {
    queue_t *queue;
    long     t0_ns;                  /* server start time */
} server_ctx;

/* Forward declaration so main() can pass &worker_thread to pthread_create. */
static void *worker_thread(void *arg);

/* Get current time as a single nanosecond count from CLOCK_MONOTONIC. */
static long now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000000000L + ts.tv_nsec;
}

int main(int argc, char *argv[]) {
    if (argc != 4) {
        fprintf(stderr, "Usage: %s port num_jobs q_size\n", argv[0]);
        return EXIT_FAILURE;
    }

    /* Parse args. Same endptr pattern as client.c — detect garbage input. */
    char *end;

    long port = strtol(argv[1], &end, 10);
    if (*end != '\0' || port < 0 || port > 65535) {
        fprintf(stderr, "invalid port: %s\n", argv[1]);
        return EXIT_FAILURE;
    }

    long num_jobs = strtol(argv[2], &end, 10);
    if (*end != '\0' || num_jobs <= 0) {
        fprintf(stderr, "invalid num_jobs: %s\n", argv[2]);
        return EXIT_FAILURE;
    }

    long q_size = strtol(argv[3], &end, 10);
    if (*end != '\0' || q_size <= 0) {
        fprintf(stderr, "invalid q_size: %s\n", argv[3]);
        return EXIT_FAILURE;
    }

    /* Initialize the synchronized queue. queue_t lives on main's stack;
     * since main() outlives the worker thread (we pthread_join before return),
     * the worker can safely hold a pointer to it. */
    queue_t queue;
    STAILQ_INIT(&queue.head);
    queue.count                  = 0;
    queue.jobs_in_system         = 0;
    queue.total_length_in_system = 0;
    queue.capacity               = (int)q_size;
    queue.done                   = 0;

    if (pthread_mutex_init(&queue.mutex, NULL) != 0) {
        perror("pthread_mutex_init");
        return EXIT_FAILURE;
    }
    if (pthread_cond_init(&queue.not_empty, NULL) != 0) {
        perror("pthread_cond_init");
        pthread_mutex_destroy(&queue.mutex);
        return EXIT_FAILURE;
    }

    /* Create the UDP socket. */
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) {
        perror("socket");
        pthread_cond_destroy(&queue.not_empty);
        pthread_mutex_destroy(&queue.mutex);
        return EXIT_FAILURE;
    }

    /* Allow quick restart without "Address already in use" — dev convenience. */
    int yes = 1;
    if (setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes)) < 0) {
        perror("setsockopt");
        close(sockfd);
        pthread_cond_destroy(&queue.not_empty);
        pthread_mutex_destroy(&queue.mutex);
        return EXIT_FAILURE;
    }

    /* Bind to the configured port on all local interfaces (INADDR_ANY). */
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons((uint16_t)port);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(sockfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(sockfd);
        pthread_cond_destroy(&queue.not_empty);
        pthread_mutex_destroy(&queue.mutex);
        return EXIT_FAILURE;
    }

    /* Record t0 (server start time). All arrival/departure timestamps in
     * the log are measured as (now - t0). Recorded just before spawning
     * the worker so both threads see the same baseline. */
    long t0_ns = now_ns();

    /* Bundle shared state for the worker via a pointer-to-struct. */
    server_ctx ctx = { .queue = &queue, .t0_ns = t0_ns };

    /* Spawn the worker thread. */
    pthread_t worker;
    int rc = pthread_create(&worker, NULL, worker_thread, &ctx);
    if (rc != 0) {
        /* pthread_* functions return error codes directly (don't set errno),
         * so we use fprintf + strerror instead of perror. */
        fprintf(stderr, "pthread_create: %s\n", strerror(rc));
        close(sockfd);
        pthread_cond_destroy(&queue.not_empty);
        pthread_mutex_destroy(&queue.mutex);
        return EXIT_FAILURE;
    }

    /* TODO 5: acceptor loop — recvfrom, build job, enqueue or drop, repeat
     *         until num_jobs received */
    long received = 0;
    while (received < num_jobs) {
        /* Wait for a 10-byte datagram. */
        uint8_t buf[10];
        struct sockaddr_in src;
        socklen_t srclen = sizeof(src);
        ssize_t n = recvfrom(sockfd, buf, sizeof(buf), 0,
                             (struct sockaddr *)&src, &srclen);

        /* Capture arrival time IMMEDIATELY — minimizes timestamp skew. */
        long arrival_ns = now_ns() - t0_ns;

        if (n < 0) {
            perror("recvfrom");
            /* Fatal — break out and proceed to shutdown. */
            break;
        }
        if (n != (ssize_t)sizeof(buf)) {
            fprintf(stderr, "recvfrom: short read (%zd bytes)\n", n);
            received++;   /* Still counts so the server can terminate. */
            continue;
        }

        /* Decode the 10-byte wire format (mirror of the client's encode). */
        uint32_t client_id, job_length_ns;
        uint16_t job_index;
        memcpy(&client_id,     buf + 0, 4);  client_id     = ntohl(client_id);
        memcpy(&job_index,     buf + 4, 2);  job_index     = ntohs(job_index);
        memcpy(&job_length_ns, buf + 6, 4);  job_length_ns = ntohl(job_length_ns);

        /* Allocate a job struct on the heap. */
        struct job *j = malloc(sizeof(*j));
        if (j == NULL) {
            perror("malloc");
            break;   /* Fatal — proceed to shutdown. */
        }
        /* Sender IP/port stored in network byte order; converted at log time. */
        j->client_ip_net   = src.sin_addr.s_addr;
        j->client_port_net = src.sin_port;
        j->client_id       = client_id;
        j->job_index       = job_index;
        j->job_length_ns   = job_length_ns;
        j->arrival_ns      = arrival_ns;

        /* Enqueue or drop, depending on current FIFO size vs capacity. */
        pthread_mutex_lock(&queue.mutex);
        if (queue.count >= queue.capacity) {
            /* Drop policy: free the job; do NOT enqueue. */
            pthread_mutex_unlock(&queue.mutex);
            free(j);
        } else {
            STAILQ_INSERT_TAIL(&queue.head, j, entries);
            queue.count++;
            queue.jobs_in_system++;
            queue.total_length_in_system += j->job_length_ns;
            pthread_cond_signal(&queue.not_empty);   /* wake worker if waiting */
            pthread_mutex_unlock(&queue.mutex);
        }

        received++;
    }

    /* TODO 6: shutdown handshake. Acquire the mutex BEFORE setting done +
     * signaling — otherwise the signal could be lost if the worker is
     * between predicate-check and cond_wait. Holding the mutex serializes
     * with the worker's predicate-check, so it cannot miss done = 1. */
    pthread_mutex_lock(&queue.mutex);
    queue.done = 1;
    pthread_cond_signal(&queue.not_empty);
    pthread_mutex_unlock(&queue.mutex);

    /* Wait for the worker to drain remaining jobs and exit. */
    pthread_join(worker, NULL);

    close(sockfd);
    pthread_cond_destroy(&queue.not_empty);
    pthread_mutex_destroy(&queue.mutex);

    (void)num_jobs;
    return 0;
}

/* Worker thread: dequeue jobs, sleep for their length, log, and free them.
 * Exits when the queue is empty AND the acceptor has set the done flag. */
static void *worker_thread(void *arg) {
    server_ctx *ctx = (server_ctx *)arg;
    queue_t *q = ctx->queue;
    long t0 = ctx->t0_ns;

    while (1) {
        /* 1. Wait for a job (or for the shutdown signal). */
        pthread_mutex_lock(&q->mutex);
        while (STAILQ_EMPTY(&q->head) && !q->done) {
            pthread_cond_wait(&q->not_empty, &q->mutex);
        }
        if (STAILQ_EMPTY(&q->head) && q->done) {
            pthread_mutex_unlock(&q->mutex);
            return NULL;
        }

        /* 2. Dequeue. count-- only — jobs_in_system stays unchanged because
         *    the job is still in the system (now being executed). */
        struct job *j = STAILQ_FIRST(&q->head);
        STAILQ_REMOVE_HEAD(&q->head, entries);
        q->count--;
        pthread_mutex_unlock(&q->mutex);

        /* 3. "Process" the job by sleeping for its length. Outside the lock
         *    so the acceptor can keep enqueuing concurrently. */
        struct timespec ts;
        ts.tv_sec  = j->job_length_ns / 1000000000L;
        ts.tv_nsec = j->job_length_ns % 1000000000L;
        nanosleep(&ts, NULL);

        /* 4. Capture departure time as soon as the sleep returns. */
        long departure_ns = now_ns() - t0;

        /* 5. Snapshot q_num/q_time. The just-finished job is still counted
         *    (we decrement AFTER logging — per lecturer clarification). */
        pthread_mutex_lock(&q->mutex);
        int  q_num  = q->jobs_in_system;
        long q_time = q->total_length_in_system;
        pthread_mutex_unlock(&q->mutex);

        /* 6. Print TSV log line. printf is slow — keep the lock released. */
        printf("%08x:%04x\t%d:%d\t%ld\t%ld\t%d\t%ld\n",
               (unsigned int)ntohl(j->client_ip_net),
               (unsigned int)ntohs(j->client_port_net),
               (int)j->client_id,
               (int)j->job_index,
               j->arrival_ns,
               departure_ns,
               q_num,
               q_time);

        /* 7. Now the job has fully left the system. Decrement and free. */
        pthread_mutex_lock(&q->mutex);
        q->jobs_in_system--;
        q->total_length_in_system -= (long)j->job_length_ns;
        pthread_mutex_unlock(&q->mutex);

        free(j);
    }
}
