"""Consume wearable events from Kafka and land them in Postgres.

Runs as part of the **consumer group** `wearable-loaders` (see __init__). Kafka
assigns partitions across the group's members; if you run several consumers they
share the 3 partitions and Kafka **rebalances** on join/leave.

Offset handling: auto-commit is OFF. We insert a batch into Postgres and only
**then commit the offsets** — so a crash mid-batch reprocesses (at-least-once).
The Postgres table has a unique event_id, and we upsert on conflict, making the
write idempotent so at-least-once doesn't create duplicates.

Usage:
    python -m streaming.consumer --max 500       # consume 500 then exit (demo)
    python -m streaming.consumer                  # run until idle/interrupted
"""

from __future__ import annotations

import argparse
import json
import os

from confluent_kafka import Consumer, KafkaError
from sqlalchemy import text

from ingestion.load_to_postgres import engine_from_env
from streaming import CONSUMER_GROUP, TOPIC

STREAM_SCHEMA = "streaming"
TABLE = "wearable_events"

DDL = f"""
create schema if not exists {STREAM_SCHEMA};
create table if not exists {STREAM_SCHEMA}.{TABLE} (
    event_id     bigint primary key,
    user_id      integer not null,
    ts           double precision not null,
    heart_rate   integer,
    steps_delta  integer,
    device       text,
    partition    integer,
    "offset"     bigint
);
"""

UPSERT = f"""
insert into {STREAM_SCHEMA}.{TABLE}
    (event_id, user_id, ts, heart_rate, steps_delta, device, partition, "offset")
values (:event_id, :user_id, :ts, :heart_rate, :steps_delta, :device, :partition, :offset)
on conflict (event_id) do nothing
"""


def build_consumer(bootstrap: str) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": CONSUMER_GROUP,
            "enable.auto.commit": False,        # we commit AFTER the DB write
            "auto.offset.reset": "earliest",    # first run reads from the start
            "client.id": "wearable-consumer",
        }
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Consume wearable events -> Postgres.")
    ap.add_argument("--max", type=int, default=0, help="stop after N messages (0 = until idle)")
    ap.add_argument("--idle-timeout", type=float, default=10.0,
                    help="exit after this many seconds with no new messages")
    args = ap.parse_args()

    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    eng = engine_from_env()
    with eng.begin() as conn:
        for stmt in DDL.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt))

    consumer = build_consumer(bootstrap)
    consumer.subscribe([TOPIC])

    consumed = 0
    idle = 0.0
    poll_s = 1.0
    try:
        while True:
            msg = consumer.poll(poll_s)
            if msg is None:
                idle += poll_s
                if args.idle_timeout and idle >= args.idle_timeout:
                    print(f"idle {idle:.0f}s, stopping")
                    break
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"  ! consumer error: {msg.error()}")
                continue

            idle = 0.0
            evt = json.loads(msg.value())
            with eng.begin() as conn:
                conn.execute(
                    text(UPSERT),
                    {
                        **{k: evt[k] for k in
                           ("event_id", "user_id", "ts", "heart_rate", "steps_delta", "device")},
                        "partition": msg.partition(),
                        "offset": msg.offset(),
                    },
                )
            # commit the offset ONLY after the row is safely in Postgres
            consumer.commit(msg, asynchronous=False)
            consumed += 1
            if consumed % 100 == 0:
                print(f"  consumed {consumed} (last: p{msg.partition()}@{msg.offset()})")
            if args.max and consumed >= args.max:
                print(f"reached --max {args.max}, stopping")
                break
    finally:
        consumer.close()
        print(f"done: {consumed} events landed in {STREAM_SCHEMA}.{TABLE}")


if __name__ == "__main__":
    main()
