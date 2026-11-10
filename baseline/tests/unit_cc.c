/**
 * Unit tests for congestion control, each checking a row of the student's
 * event table (section 3) or their revised duplicate-ACK rule (section 4).
 * Includes backend.c directly so static functions (check_timer) are callable.
 * Link with cmu_packet.o and cmu_tcp.o only (not backend.o).
 */

#include "../src/backend.c"

#define M ((uint32_t)MSS)
#define X 1000u
#define OUT 60000u  // Bytes outstanding; inside the 65535 window.
#define BIG 65535

static int fails = 0;

static void expect_u(const char *name, uint32_t got, uint32_t want) {
  if (got != want) fails++;
  printf("  [%s] %s: got %u, want %u\n", got == want ? "PASS" : "FAIL", name,
         got, want);
}

static const char *st(cc_state_t s) { return cc_name(s); }

static void expect_state(const char *name, cc_state_t got, cc_state_t want) {
  if (got != want) fails++;
  printf("  [%s] %s: got %s, want %s\n", got == want ? "PASS" : "FAIL", name,
         st(got), st(want));
}

static void make_sock(cmu_socket_t *s, cc_state_t state, uint32_t cwnd,
                      uint32_t ssthresh) {
  memset(s, 0, sizeof(*s));
  pthread_mutex_init(&s->send_lock, NULL);
  pthread_mutex_init(&s->recv_lock, NULL);
  s->socket = -1;  // sendto() fails harmlessly.
  s->conn_state = ESTABLISHED;
  s->window.last_ack_received = X;
  s->window.next_seq_to_send = X + OUT;
  s->window.max_seq_sent = X + OUT;
  s->window.right_edge = X + BIG;
  s->sending_buf = calloc(OUT, 1);
  s->sending_len = OUT;
  s->cwnd = cwnd;
  s->ssthresh = ssthresh;
  s->cc_state = state;
  s->timer_running = 1;
  clock_gettime(CLOCK_MONOTONIC, &s->timer_start);
}

static void new_ack(cmu_socket_t *s) {
  handle_ack(s, 0, s->window.last_ack_received + M, BIG, 0);
}
static void dup_ack(cmu_socket_t *s, uint16_t adv, uint16_t payload) {
  handle_ack(s, 0, s->window.last_ack_received, adv, payload);
}
static void fire_timeout(cmu_socket_t *s) {
  s->timer_running = 1;
  clock_gettime(CLOCK_MONOTONIC, &s->timer_start);
  s->timer_start.tv_sec -= DEFAULT_TIMEOUT / 1000 + 1;
  check_timer(s);
}

int main(void) {
  cmu_socket_t s;

  printf("SS new ACK: cwnd += MSS (doubles per window of ACKs)\n");
  make_sock(&s, SLOW_START, M, 64 * M);
  new_ack(&s);
  expect_u("1 ACK: cwnd", s.cwnd, 2 * M);
  new_ack(&s);
  new_ack(&s);
  expect_u("2 more ACKs (one window): cwnd", s.cwnd, 4 * M);
  for (int i = 0; i < 4; i++) new_ack(&s);
  expect_u("4 more ACKs (one window): cwnd", s.cwnd, 8 * M);
  expect_state("still SS", s.cc_state, SLOW_START);

  printf("SS new ACK: cwnd >= ssthresh -> CA\n");
  make_sock(&s, SLOW_START, 2 * M, 4 * M);
  new_ack(&s);
  expect_state("cwnd 3M < 4M: state", s.cc_state, SLOW_START);
  new_ack(&s);
  expect_u("cwnd", s.cwnd, 4 * M);
  expect_state("cwnd 4M >= 4M: state", s.cc_state, CONG_AVOID);

  printf("CA new ACK: +1 MSS per cwnd's worth of ACKs\n");
  make_sock(&s, CONG_AVOID, 4 * M, 4 * M);
  for (int i = 0; i < 3; i++) new_ack(&s);
  expect_u("3 of 4 ACKs: cwnd", s.cwnd, 4 * M);
  new_ack(&s);
  expect_u("4 of 4 ACKs: cwnd", s.cwnd, 5 * M);
  for (int i = 0; i < 5; i++) new_ack(&s);
  expect_u("5 more ACKs: cwnd", s.cwnd, 6 * M);
  expect_state("still CA", s.cc_state, CONG_AVOID);

  printf("CA dup ACKs: at 3 -> halve, cwnd = ssthresh + 3MSS, FR\n");
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  dup_ack(&s, BIG, 0);
  dup_ack(&s, BIG, 0);
  expect_u("2 dups: cwnd unchanged", s.cwnd, 10 * M);
  expect_state("2 dups: state", s.cc_state, CONG_AVOID);
  expect_u("2 dups: no fast retransmit", s.fast_retx_pending, 0);
  dup_ack(&s, BIG, 0);
  expect_u("3rd dup: ssthresh", s.ssthresh, 5 * M);
  expect_u("3rd dup: cwnd", s.cwnd, 8 * M);
  expect_state("3rd dup: state", s.cc_state, FAST_RECOVERY);
  expect_u("3rd dup: fast retransmit pending", s.fast_retx_pending, 1);
  uint32_t next_before = s.window.next_seq_to_send;
  send_window(&s);
  expect_u("fast retx leaves next_seq_to_send", s.window.next_seq_to_send >=
           next_before, 1);

  printf("FR dup ACK: cwnd += MSS; FR new ACK: cwnd = ssthresh, CA\n");
  dup_ack(&s, BIG, 0);
  expect_u("FR dup: cwnd", s.cwnd, 9 * M);
  expect_state("FR dup: state", s.cc_state, FAST_RECOVERY);
  new_ack(&s);
  expect_u("FR new ACK: cwnd", s.cwnd, 5 * M);
  expect_state("FR new ACK: state", s.cc_state, CONG_AVOID);
  expect_u("FR new ACK: dup_acks", s.dup_acks, 0);

  printf("SS dup ACKs: at 3 -> FR (same as CA)\n");
  make_sock(&s, SLOW_START, 8 * M, 64 * M);
  for (int i = 0; i < 3; i++) dup_ack(&s, BIG, 0);
  expect_u("ssthresh", s.ssthresh, 4 * M);
  expect_u("cwnd", s.cwnd, 7 * M);
  expect_state("state", s.cc_state, FAST_RECOVERY);

  printf("Timeout from CA -> halve, cwnd = initial, SS, go-back-N\n");
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  fire_timeout(&s);
  expect_u("ssthresh", s.ssthresh, 5 * M);
  expect_u("cwnd", s.cwnd, WINDOW_INITIAL_WINDOW_SIZE);
  expect_state("state", s.cc_state, SLOW_START);
  expect_u("next_seq_to_send = last_ack", s.window.next_seq_to_send, X);

  printf("Timeout from FR (inflated cwnd) -> SS, ssthresh = cwnd/2\n");
  make_sock(&s, FAST_RECOVERY, 9 * M, 4 * M);
  fire_timeout(&s);
  expect_u("ssthresh", s.ssthresh, 9 * M / 2);
  expect_u("cwnd", s.cwnd, WINDOW_INITIAL_WINDOW_SIZE);
  expect_state("state", s.cc_state, SLOW_START);

  printf("halve() floor: ssthresh >= 2 MSS\n");
  make_sock(&s, CONG_AVOID, 2 * M, 2 * M);
  fire_timeout(&s);
  expect_u("ssthresh", s.ssthresh, 2 * M);

  printf("Probe timeout (rwnd closed) -> no CC change\n");
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  s.window.right_edge = X;
  s.window.next_seq_to_send = X + 1;
  s.window.max_seq_sent = X + 1;
  fire_timeout(&s);
  expect_u("cwnd", s.cwnd, 10 * M);
  expect_u("ssthresh", s.ssthresh, 4 * M);
  expect_state("state", s.cc_state, CONG_AVOID);
  expect_u("probe resent: next_seq_to_send = last_ack",
           s.window.next_seq_to_send, X);

  printf("Dup rule exclusions\n");
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  for (int i = 0; i < 3; i++) dup_ack(&s, BIG, 100);
  expect_u("ACKs carrying data: dup_acks", s.dup_acks, 0);
  for (int i = 0; i < 3; i++) dup_ack(&s, 0, 0);
  expect_u("adv = 0 (probe replies): dup_acks", s.dup_acks, 0);
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  s.window.right_edge = X;  // Window closed before the ACK.
  dup_ack(&s, BIG, 0);
  expect_u("window update after closed window: dup_acks", s.dup_acks, 0);
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  s.window.max_seq_sent = X;  // Nothing outstanding.
  s.window.next_seq_to_send = X;
  for (int i = 0; i < 3; i++) dup_ack(&s, BIG, 0);
  expect_u("nothing outstanding: dup_acks", s.dup_acks, 0);

  printf("Dup rule: growing adv still counts\n");
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);
  s.window.right_edge = X + 30000;
  s.window.next_seq_to_send = X + 20000;  // Sent only inside the window.
  s.window.max_seq_sent = X + 20000;
  dup_ack(&s, 40000, 0);
  dup_ack(&s, 41000, 0);
  dup_ack(&s, 42000, 0);
  expect_state("3 dups with growing adv: state", s.cc_state, FAST_RECOVERY);
  expect_u("right_edge followed adv", s.window.right_edge, X + 42000);

  printf("Dup rule: receiver dropped data past a shrunk edge\n");
  make_sock(&s, CONG_AVOID, 10 * M, 4 * M);  // 60000 outstanding.
  for (int i = 0; i < 3; i++) dup_ack(&s, 30000, 0);
  expect_u("ack + adv < max_seq_sent: dup_acks", s.dup_acks, 0);
  expect_state("no FR", s.cc_state, CONG_AVOID);

  printf(fails ? "\nTest Failed (%d)\n" : "\nTest Passed\n", fails);
  return fails != 0;
}
