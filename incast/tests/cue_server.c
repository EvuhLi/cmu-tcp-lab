/**
 * Test-only listener for test_cp2_flow.py. Never reads on its own. When
 * /tmp/cue_read appears (containing N), it reads up to N bytes with NO_WAIT,
 * deletes the cue, and writes the byte count to /tmp/cue_done.
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "cmu_tcp.h"

#define CUE "/tmp/cue_read"
#define DONE "/tmp/cue_done"

int main(void) {
  cmu_socket_t socket;
  static uint8_t buf[MAX_NETWORK_BUFFER];
  char *serverip = getenv("server15441");
  char *serverport = getenv("serverport15441");
  if (!serverip) serverip = "10.0.1.1";
  if (!serverport) serverport = "15441";
  unlink(CUE);
  unlink(DONE);

  if (cmu_socket(&socket, TCP_LISTENER, (uint16_t)atoi(serverport), serverip) <
      0)
    exit(EXIT_FAILURE);

  for (int i = 0; i < 1200; i++) {  // ~60 s, then exit.
    FILE *f = fopen(CUE, "r");
    if (f != NULL) {
      int want = 0, got = 0, n;
      if (fscanf(f, "%d", &want) != 1) want = 0;
      fclose(f);
      unlink(CUE);
      while (got < want &&
             (n = cmu_read(&socket, buf, want - got, NO_WAIT)) > 0) {
        got += n;
      }
      FILE *d = fopen(DONE, "w");
      fprintf(d, "%d\n", got);
      fclose(d);
    }
    usleep(50000);
  }
  return EXIT_SUCCESS;
}
