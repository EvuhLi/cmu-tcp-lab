#!/usr/bin/env python3
"""Black-box fast-retransmit test against the real stack (tests/testing_server
as sender). Student's design, section 6: on the 3rd duplicate ACK, resend
exactly one segment starting at last_ack_received, without waiting for the
timeout.

Scenario: ACK the first segment (cwnd 1 -> 2 MSS, sender sends 2 more), then
send duplicate ACKs for that same number.
  - after 2 dups: no retransmission of last_ack
  - after the 3rd: a segment at seq = last_ack, well before DEFAULT_TIMEOUT
"""

import time

from fabric import Connection
from scapy.all import send

from test_cp2_flow import (
    CMUTCP, IFNAME, START, TESTING_HOST_IP, Raw, handshake, pkt,
    sniffer_start, start, stop,
)

MSS = 1375
results = []


def check(name, cond, detail):
    results.append(cond)
    print(f"[{name}] {'PASS' if cond else 'FAIL'}: {detail}")


def data_pkts(sniffer):
    return [p for p in sniffer.stop() if CMUTCP in p and Raw in p]


def main():
    with Connection(host=TESTING_HOST_IP, user="vagrant",
                    connect_kwargs={"password": "vagrant"}) as conn:
        start(conn, "testing_server")
        try:
            srv = handshake()
            sn = sniffer_start()
            send(pkt(START, srv, payload=b"go"), iface=IFNAME, verbose=0)
            time.sleep(0.5)
            first = data_pkts(sn)
            check("setup: 1 segment (cwnd = 1 MSS)", len(first) == 1,
                  f"{len(first)} data pkts")

            sn = sniffer_start()
            send(pkt(START + 2, srv + MSS), iface=IFNAME, verbose=0)
            time.sleep(0.5)
            burst = data_pkts(sn)
            check("setup: 2 segments after new ACK (cwnd = 2 MSS)",
                  len(burst) == 2, f"{len(burst)} data pkts")

            dup = pkt(START + 2, srv + MSS)
            sn = sniffer_start()
            send([dup, dup], iface=IFNAME, verbose=0)
            time.sleep(0.5)
            retx = [p for p in data_pkts(sn)
                    if p[CMUTCP].seq_num == srv + MSS]
            check("2 dups: no retransmission", not retx,
                  f"{len(retx)} segments at seq=last_ack")

            sn = sniffer_start()
            t0 = time.time()
            send(dup, iface=IFNAME, verbose=0)
            time.sleep(0.5)
            pkts = data_pkts(sn)
            retx = [p for p in pkts if p[CMUTCP].seq_num == srv + MSS]
            dt = (retx[0].time - t0) if retx else None
            check("3rd dup: one segment at seq=last_ack, before timeout",
                  len(retx) == 1 and len(retx[0][Raw].load) == MSS
                  and dt < 1.0,
                  f"{len(retx)} retransmissions"
                  + (f", {len(retx[0][Raw].load)} bytes, {dt*1000:.0f} ms "
                     "after 3rd dup" if retx else ""))
        finally:
            stop(conn)
    print("Test Passed" if all(results) else "Test Failed")


if __name__ == "__main__":
    main()
