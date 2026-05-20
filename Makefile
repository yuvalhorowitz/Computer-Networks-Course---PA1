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
