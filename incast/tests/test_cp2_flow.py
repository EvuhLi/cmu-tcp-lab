#!/usr/bin/env python3
"""CP2 flow-control tests, each checking a claim from the student's design.

Expected values use the student's formula
    adv_window = MAX_NETWORK_BUFFER - (unread in-order bytes)
with MAX_NETWORK_BUFFER = 65535.

Receiver tests (scapy is the initiator, tests/cue_server is the listener and
only reads when cued):
  R1  trace (a): 4000 in-order bytes -> ack +4000, win 61535
  R2  trace (b): [6000,7000) past a gap -> ack and window unchanged
  R3  trace (c): app reads 3000 -> nothing sent right away; next ACK carries
      window 64535
  R4  design (2): filling the gap drains the out-of-order data
  R5  "drop anything past the right edge": a segment crossing the edge is
      trimmed, ACK lands on the edge with window 0
  R6  design (4): a probe into a zero window is dropped but still ACKed, win 0
  R7  design (3): app read after a zero window -> unsolicited window update
  R8  design (4): probe after the window opens is accepted, ack advances by 1

Sender tests (scapy is the initiator, tests/testing_server sends
tests/random.input, 10240 bytes, after its first read):
  S1  sender never sends past ack + advertised window (window 3000)
  S2  window 0 -> 1-byte probe; GBN timer retransmits it; an opening ACK
      resumes sending without passing the new right edge
"""

import time

from fabric import Connection
from scapy.all import AsyncSniffer, Raw, send, sr1

from common import (
    CMUTCP,
    ACK_MASK,
    IFNAME,
    SYN_MASK,
    STOP_TESTING_SERVER_CMD,
    TESTING_HOST_IP,
    TESTING_HOST_PORT,
    ip,
    udp,
)

MAX = 65535
ISN = 1000
START = ISN + 1
T = 3
CODE = "/vagrant/project-2_15-441/tests"
FILTER = f"udp and src host {TESTING_HOST_IP} and src port {TESTING_HOST_PORT}"

results = []


def check(name, cond, detail):
    results.append((name, cond))
    print(f"[{name}] {'PASS' if cond else 'FAIL'}: {detail}")


def pkt(seq, ack, flags=ACK_MASK, payload=b"", win=MAX):
    p = ip / udp / CMUTCP(plen=25 + len(payload), seq_num=seq, ack_num=ack,
                          flags=flags, advertised_window=win)
    return p / Raw(load=payload) if payload else p


def ack_str(p):
    if p is None:
        return "no reply"
    return f"ack={p[CMUTCP].ack_num - START} win={p[CMUTCP].advertised_window}"


def expect_ack(name, reply, rel_ack, win):
    ok = (reply is not None and reply[CMUTCP].ack_num == START + rel_ack
          and reply[CMUTCP].advertised_window == win)
    check(name, ok, f"{ack_str(reply)} (want ack={rel_ack} win={win})")


def handshake(win=MAX):
    synack = sr1(pkt(ISN, 0, SYN_MASK, win=win), timeout=T, iface=IFNAME,
                 verbose=0)
    if synack is None or synack[CMUTCP].flags != SYN_MASK | ACK_MASK:
        raise RuntimeError("no SYN-ACK")
    srv = synack[CMUTCP].seq_num + 1
    send(pkt(START, srv, win=win), iface=IFNAME, verbose=0)
    time.sleep(0.2)
    return srv


def send_data(rel, srv, payload):
    return sr1(pkt(START + rel, srv, payload=payload), timeout=T,
               iface=IFNAME, verbose=0)


def cue_read(conn, n):
    conn.run(f"rm -f /tmp/cue_done; echo {n} > /tmp/cue_read", hide=True)
    for _ in range(40):
        r = conn.run("cat /tmp/cue_done 2>/dev/null || true", hide=True)
        if r.stdout.strip():
            return int(r.stdout.strip())
        time.sleep(0.1)
    raise RuntimeError("cue_server did not read")


def sniffer_start():
    s = AsyncSniffer(iface=IFNAME, filter=FILTER)
    s.start()
    time.sleep(0.5)  # Let the sniffer attach before triggering traffic.
    return s


def start(conn, binary):
    conn.run(f"tmux new -s pytest_server -d {CODE}/{binary}")
    time.sleep(0.5)


def stop(conn):
    try:
        conn.run(STOP_TESTING_SERVER_CMD, hide=True)
    except Exception:
        pass


def receiver_trace_tests(conn):
    """R1-R4 on one connection."""
    start(conn, "cue_server")
    try:
        srv = handshake()
        r = None
        for i in range(4):
            r = send_data(i * 1000, srv, b"a" * 1000)
        expect_ack("R1 trace (a)", r, 4000, MAX - 4000)

        r = send_data(6000, srv, b"b" * 1000)
        expect_ack("R2 trace (b)", r, 4000, MAX - 4000)

        sniffer = sniffer_start()
        got = cue_read(conn, 3000)
        time.sleep(1.0)
        unsolicited = [p for p in sniffer.stop() if CMUTCP in p]
        check("R3 trace (c) nothing sent", got == 3000 and not unsolicited,
              f"read {got}, {len(unsolicited)} packet(s) sent after read")
        r = send_data(0, srv, b"a" * 1000)  # Duplicate data elicits an ACK.
        expect_ack("R3 trace (c) next ACK", r, 4000, MAX - 1000)

        r = send_data(4000, srv, b"c" * 1000)
        expect_ack("R4 gap partly filled", r, 5000, MAX - 2000)
        r = send_data(5000, srv, b"c" * 1000)
        expect_ack("R4 gap filled, drained", r, 7000, MAX - 4000)
    finally:
        stop(conn)


def receiver_edge_tests(conn):
    """R5-R8 on one connection."""
    start(conn, "cue_server")
    try:
        srv = handshake()
        r = None
        for i in range(65):
            r = send_data(i * 1000, srv, b"x" * 1000)
        expect_ack("R5 setup: 65000 in order", r, 65000, MAX - 65000)
        r = send_data(65000, srv, b"y" * 1000)  # Crosses edge at 65535.
        expect_ack("R5 trimmed at right edge", r, MAX, 0)

        r = send_data(MAX, srv, b"p")
        expect_ack("R6 probe into zero window", r, MAX, 0)

        sniffer = sniffer_start()
        cue_read(conn, 3000)
        time.sleep(1.0)
        ups = [p for p in sniffer.stop() if CMUTCP in p]
        upd = ups[0] if ups else None
        expect_ack("R7 window-update ACK", upd, MAX, 3000)

        r = send_data(MAX, srv, b"p")
        expect_ack("R8 probe accepted after opening", r, MAX + 1, 2999)
    finally:
        stop(conn)


def sender_window_test(conn):
    """S1: advertised window 3000."""
    start(conn, "testing_server")
    try:
        srv = handshake(win=3000)
        sniffer = sniffer_start()
        send(pkt(START, srv, payload=b"go", win=3000), iface=IFNAME,
             verbose=0)
        time.sleep(1.5)
        data = [p for p in sniffer.stop() if CMUTCP in p and Raw in p]
        top = max((p[CMUTCP].seq_num + len(p[Raw].load) - srv for p in data),
                  default=0)
        # With congestion control the limit is min(cwnd, rwnd), and cwnd
        # starts at WINDOW_INITIAL_WINDOW_SIZE (1 MSS = 1375 by default).
        want = min(1375, 3000)
        check("S1 stays within min(cwnd, rwnd)", data and top == want,
              f"{len(data)} data pkts, highest byte sent = {top} "
              f"(want exactly {want})")
    finally:
        stop(conn)


def sender_probe_test(conn):
    """S2: advertised window 0, then opened to 3000."""
    start(conn, "testing_server")
    try:
        srv = handshake(win=0)
        sniffer = sniffer_start()
        send(pkt(START, srv, payload=b"go", win=0), iface=IFNAME, verbose=0)
        time.sleep(4.0)  # > DEFAULT_TIMEOUT so the probe gets retransmitted.
        data = [p for p in sniffer.stop() if CMUTCP in p and Raw in p]
        probes = [p for p in data
                  if p[CMUTCP].seq_num == srv and len(p[Raw].load) == 1]
        check("S2 1-byte probe sent", len(probes) >= 1 and len(data) ==
              len(probes), f"{len(data)} data pkts, {len(probes)} 1-byte "
              "probes at the first unsent byte")
        check("S2 probe retransmitted by timer", len(probes) >= 2,
              f"{len(probes)} probe transmissions in 4 s")

        sniffer = sniffer_start()
        send(pkt(START + 2, srv, win=3000), iface=IFNAME, verbose=0)
        time.sleep(1.5)
        data = [p for p in sniffer.stop() if CMUTCP in p and Raw in p]
        top = max((p[CMUTCP].seq_num + len(p[Raw].load) - srv for p in data),
                  default=0)
        check("S2 resumes within new edge", data and 0 < top <= 3000,
              f"{len(data)} data pkts after window opened, highest byte = "
              f"{top} (want 0 < x <= 3000)")
    finally:
        stop(conn)


def sender_shrink_test(conn):
    """S3: the scenario that failed on Gradescope. Handshake window 65535,
    then the receiver ACKs S+2750 with adv 0 while S+[2750, 4125) is out.
    Student's revised design: accept the shrink, pull next_seq_to_send back,
    probe right away, and resume on a window-only update."""
    M = 1375
    start(conn, "testing_server")
    try:
        srv = handshake()
        sn = sniffer_start()
        send(pkt(START, srv, payload=b"go"), iface=IFNAME, verbose=0)
        time.sleep(0.5)
        sn.stop()
        sn = sniffer_start()
        send(pkt(START + 2, srv + M), iface=IFNAME, verbose=0)  # cwnd -> 2M
        time.sleep(0.5)
        sn.stop()

        sn = sniffer_start()
        send(pkt(START + 2, srv + 2 * M, win=0), iface=IFNAME, verbose=0)
        time.sleep(1.0)
        data = [p for p in sn.stop() if CMUTCP in p and Raw in p]
        new = [p for p in data if p[CMUTCP].seq_num >= srv + 3 * M]
        probes = [p for p in data if p[CMUTCP].seq_num == srv + 2 * M
                  and len(p[Raw].load) == 1]
        check("S3 stops on shrink to 0", not new,
              f"{len(new)} new-data pkts after adv=0")
        check("S3 probes right away (no 3 s wait)", len(probes) >= 1
              and probes[0].time - data[0].time < 0.5 if data else False,
              f"{len(probes)} probe(s) within 1 s")

        sn = sniffer_start()
        send(pkt(START + 2, srv + 2 * M, win=0), iface=IFNAME, verbose=0)
        time.sleep(1.0)
        after_reply = [p for p in sn.stop() if CMUTCP in p and Raw in p]
        print(f"[S3 info] one adv=0 reply to a probe -> "
              f"{len(after_reply)} probe(s) sent within 1 s")

        sn = sniffer_start()
        send(pkt(START + 2, srv + 2 * M, win=5000), iface=IFNAME, verbose=0)
        time.sleep(1.0)
        data = [p for p in sn.stop() if CMUTCP in p and Raw in p]
        top = max((p[CMUTCP].seq_num + len(p[Raw].load) - srv for p in data),
                  default=0)
        check("S3 window-only update restarts sender",
              data and 2 * M < top <= 2 * M + 5000,
              f"{len(data)} data pkts, highest byte = {top} "
              f"(want {2 * M} < x <= {2 * M + 5000})")
    finally:
        stop(conn)


if __name__ == "__main__":
    with Connection(host=TESTING_HOST_IP, user="vagrant",
                    connect_kwargs={"password": "vagrant"}) as c:
        for t in (receiver_trace_tests, receiver_edge_tests,
                  sender_window_test, sender_probe_test, sender_shrink_test):
            try:
                t(c)
            except Exception as e:  # Keep going so every test reports.
                check(t.__name__, False, f"exception: {e}")
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    print("Test Passed" if not failed else f"Test Failed: {failed}")
