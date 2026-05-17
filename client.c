#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>
#include <time.h>
#include <stdint.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

/* Sample an exponentially distributed random number with rate `lambda`.
 * Uses inverse-transform method on the result of rand(). */
static double randexp(double lambda) {
    double u = rand() / ((double)RAND_MAX + 1.0);
    return -log(1.0 - u) / lambda;
}

int main(int argc, char *argv[]) {
    if (argc != 7) {
        fprintf(stderr,
                "Usage: %s ip port num_jobs seed lambda mu\n",
                argv[0]);
        return EXIT_FAILURE;
    }

    /* Parse args. We use strtol/strtod (instead of atoi/atof) so we can
     * detect garbage input via the endptr trick. */
    char *end;

    /* port (host byte order, will convert to network with htons later) */
    long port = strtol(argv[2], &end, 10);
    if (*end != '\0' || port < 0 || port > 65535) {
        fprintf(stderr, "invalid port: %s\n", argv[2]);
        return EXIT_FAILURE;
    }

    long num_jobs = strtol(argv[3], &end, 10);
    if (*end != '\0' || num_jobs < 0) {
        fprintf(stderr, "invalid num_jobs: %s\n", argv[3]);
        return EXIT_FAILURE;
    }

    long seed = strtol(argv[4], &end, 10);
    if (*end != '\0') {
        fprintf(stderr, "invalid seed: %s\n", argv[4]);
        return EXIT_FAILURE;
    }

    double lambda = strtod(argv[5], &end);
    if (*end != '\0' || lambda <= 0.0) {
        fprintf(stderr, "invalid lambda: %s\n", argv[5]);
        return EXIT_FAILURE;
    }

    double mu = strtod(argv[6], &end);
    if (*end != '\0' || mu <= 0.0) {
        fprintf(stderr, "invalid mu: %s\n", argv[6]);
        return EXIT_FAILURE;
    }

    /* Build the destination address. inet_pton parses dotted-decimal IP. */
    struct sockaddr_in dest;
    memset(&dest, 0, sizeof(dest));
    dest.sin_family = AF_INET;
    dest.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, argv[1], &dest.sin_addr) != 1) {
        fprintf(stderr, "invalid ip: %s\n", argv[1]);
        return EXIT_FAILURE;
    }

    /* Seed the RNG. Must be called once, before any rand(). */
    srand((unsigned int)seed);

    /* Create UDP socket: IPv4 (AF_INET), datagram (SOCK_DGRAM), default proto. */
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }

    /* Pre-compute values used inside the loop. */
    uint32_t client_id = (uint32_t)getpid();
    uint32_t ip_host   = ntohl(dest.sin_addr.s_addr);
    uint16_t port_host = ntohs(dest.sin_port);

    /* Main job-generation loop. The order of rand() calls (x then y) must
     * match the spec exactly — extra calls would shift the sequence. */
    for (long i = 0; i < num_jobs; i++) {
        /* 1. Sample inter-arrival time x (ms) and sleep 1e6 * x nanoseconds. */
        double x = randexp(lambda);
        long sleep_ns = (long)floor(1e6 * x);

        struct timespec ts;
        ts.tv_sec  = sleep_ns / 1000000000L;
        ts.tv_nsec = sleep_ns % 1000000000L;
        nanosleep(&ts, NULL);

        /* 2. Sample job length y (ms); the wire format carries 1e6 * y. */
        double y = randexp(mu);
        uint32_t job_length_ns = (uint32_t)floor(1e6 * y);

        /* 3. Build the 10-byte message in network byte order. */
        uint8_t msg[10];
        uint32_t net_id  = htonl(client_id);
        uint16_t net_idx = htons((uint16_t)i);
        uint32_t net_len = htonl(job_length_ns);
        memcpy(msg + 0, &net_id,  4);
        memcpy(msg + 4, &net_idx, 2);
        memcpy(msg + 6, &net_len, 4);

        /* 4. Send the datagram. */
        ssize_t n = sendto(sockfd, msg, sizeof(msg), 0,
                           (struct sockaddr *)&dest, sizeof(dest));
        if (n != (ssize_t)sizeof(msg)) {
            perror("sendto");
            close(sockfd);
            return EXIT_FAILURE;
        }

        /* 5. Log the TSV line: ip:port  id:index  floor_x  floor_y */
        printf("%08x:%04x\t%d:%d\t%d\t%u\n",
               ip_host, port_host,
               (int)client_id, (int)i,
               (int)sleep_ns, (unsigned int)job_length_ns);
    }

    close(sockfd);
    return 0;
}
