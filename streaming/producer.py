"""Produce synthetic real-time wearable events, keyed by user_id.

Each event is a single heart-rate + steps reading "now" for a random user.
Events are **keyed by user_id** so all of one user's events go to the same
partition (per-user ordering). We use **acks=all** so a write is only considered
successful once all in-sync replicas have it (strongest durability).

Usage:
    python -m streaming.producer --count 500 --rate 50
    python -m streaming.producer --count 0           # stream forever
"""

from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
from confluent_kafka import Producer

from streaming import TOPIC


def build_producer(bootstrap: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap,
            "acks": "all",                 # wait for all in-sync replicas
            "enable.idempotence": True,     # no duplicates on retry
            "linger.ms": 20,                # small batching for throughput
            "client.id": "wearable-producer",
        }
    )


def make_event(rng: np.random.Generator, n_users: int, seq: int) -> dict:
    user_id = int(rng.integers(1, n_users + 1))
    # a plausible instantaneous reading
    hr = int(np.clip(rng.normal(75, 18), 40, 195))
    steps = int(max(0, rng.normal(40, 30)))
    return {
        "event_id": seq,
        "user_id": user_id,
        "ts": time.time(),
        "heart_rate": hr,
        "steps_delta": steps,
        "device": rng.choice(["Xiaomi", "Huawei", "Apple"]).item(),
    }


def _on_delivery(err, msg):
    if err is not None:
        print(f"  ! delivery failed: {err}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Stream synthetic wearable events.")
    ap.add_argument("--count", type=int, default=500, help="events to send (0 = forever)")
    ap.add_argument("--rate", type=float, default=50, help="events per second")
    ap.add_argument("--users", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    p = build_producer(bootstrap)
    rng = np.random.default_rng(args.seed)

    sent = 0
    interval = 1.0 / args.rate if args.rate > 0 else 0
    try:
        while args.count == 0 or sent < args.count:
            evt = make_event(rng, args.users, sent)
            p.produce(
                TOPIC,
                key=str(evt["user_id"]),          # partition by user_id
                value=json.dumps(evt).encode(),
                on_delivery=_on_delivery,
            )
            p.poll(0)                              # serve delivery callbacks
            sent += 1
            if sent % 100 == 0:
                print(f"  produced {sent} events")
            if interval:
                time.sleep(interval)
    finally:
        p.flush(10)
        print(f"done: {sent} events flushed to topic '{TOPIC}'")


if __name__ == "__main__":
    main()
