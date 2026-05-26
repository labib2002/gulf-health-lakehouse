"""Create the wearable-events topic with a deliberate partition count.

Topic design (see ADR-0007):
* 3 partitions so a consumer group can scale to up to 3 parallel consumers.
* Keyed by user_id (in the producer) so all of a user's events land on the SAME
  partition -> per-user ordering is preserved.
"""

from __future__ import annotations

import os
import sys

from confluent_kafka.admin import AdminClient, NewTopic

from streaming import NUM_PARTITIONS, TOPIC


def main() -> None:
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    admin = AdminClient({"bootstrap.servers": bootstrap})

    topic = NewTopic(TOPIC, num_partitions=NUM_PARTITIONS, replication_factor=1)
    futures = admin.create_topics([topic])
    for name, fut in futures.items():
        try:
            fut.result()
            print(f"created topic {name} ({NUM_PARTITIONS} partitions)")
        except Exception as exc:  # already exists is fine
            if "already exists" in str(exc).lower():
                print(f"topic {name} already exists")
            else:
                print(f"failed to create {name}: {exc}", file=sys.stderr)
                raise


if __name__ == "__main__":
    main()
