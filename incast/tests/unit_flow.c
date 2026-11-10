/**
 * Unit test for the sender's ACK handling (handle_ack), per the student's
 * revised pseudocode (WL1/WL2 rule):
 *   - the most recently arrived ACK that isn't older sets right_edge, which
 *     may shrink; a reordered same-seq/same-ack ACK is accepted (known cost)
 *   - ACKs with ack < last_ack are ignored entirely.
 *   - a shrink below next_seq_to_send pulls next_seq_to_send back.
 */

#include <pthread.h>
#include <stdio.h>
#include <string.h>

#include "cmu_tcp.h"

void handle_ack(cmu_socket_t *sock, uint32_t seq, uint32_t ack, uint16_t adv,
                uint16_t payload_len);

static int fails = 0;
static void expect(const char *name, uint32_t got, uint32_t want) {
  int ok = got == want;
  if (!ok) fails++;
  printf("[%s] %s: right_edge=%u (want %u)\n", name, ok ? "PASS" : "FAIL",
         got, want);
}

int main(void) {
  cmu_socket_t s;
  memset(&s, 0, sizeof(s));
  pthread_mutex_init(&s.send_lock, NULL);
  const uint32_t X = 5000;
  s.window.last_ack_received = X;
  s.window.next_seq_to_send = X;
  s.window.max_seq_sent = X;
  s.window.right_edge = X;

  const uint32_t SEQ = 777;
  s.window.wl1 = SEQ;
  s.window.wl2 = X;

  handle_ack(&s, SEQ, X, 4000, 0);
  expect("ack X win 4000", s.window.right_edge, X + 4000);

  handle_ack(&s, SEQ, X, 0, 0);  // Same seq/ack, window 0: accepted.
  expect("same seq/ack win 0 (accepted)", s.window.right_edge, X);

  handle_ack(&s, SEQ, X, 4000, 0);
  handle_ack(&s, SEQ, X - 10, 60000, 0);  // ack < last_ack: ignored.
  expect("ack < last_ack", s.window.right_edge, X + 4000);

  handle_ack(&s, SEQ - 5, X, 60000, 0);  // seq older than wl1: ignored.
  expect("seq < wl1", s.window.right_edge, X + 4000);

  // Shrink below data already sent: next_seq_to_send pulled back to edge.
  s.window.next_seq_to_send = X + 4000;
  s.window.max_seq_sent = X + 4000;
  handle_ack(&s, SEQ, X, 1000, 0);
  expect("shrink: right_edge", s.window.right_edge, X + 1000);
  expect("shrink: next_seq_to_send pulled back", s.window.next_seq_to_send,
         X + 1000);

  printf(fails ? "Test Failed\n" : "Test Passed\n");
  return fails != 0;
}
