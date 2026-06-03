# Kafka streaming (Phase 6)

Single-broker Kafka (**KRaft**, no ZooKeeper) streaming synthetic wearable events
producer → topic → consumer → Postgres. Scope is **producer/consumer + topic
design**, not cluster ops. See [ADR-0007](../docs/adr/0007-kafka.md) and the
[topology diagram](../docs/kafka_topology.md).

## Run it

```bash
docker compose up -d postgres                                # base (shared net)
docker compose -f streaming/docker-compose.kafka.yml up -d   # kafka (KRaft)

export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export POSTGRES_HOST=localhost POSTGRES_PORT=5433

python -m streaming.create_topic        # wearable-events, 3 partitions
python -m streaming.producer --count 500 --rate 200   # keyed by user_id, acks=all
python -m streaming.consumer --max 500                # group wearable-loaders -> Postgres
```

Scale the consumer group by running `python -m streaming.consumer` in two
terminals — Kafka splits the 3 partitions across them.

## Verified locally

- 500 events produced (acks=all) and consumed into `streaming.wearable_events`.
- Spread across all 3 partitions (155 / 172 / 173).
- **Per-user ordering**: 0 users span more than one partition (key = user_id).
- **Group sharing**: two consumers split 600 events 186 / 414 (2-vs-1 partitions).
- **Idempotent at-least-once**: offsets are committed only after the DB write, and
  the upsert (`on conflict do nothing`) means reprocessing creates no duplicates.

> Note: the demo producer sets `event_id = sequence` per run, so a second run's
> ids collide with the first and dedupe — handy to show idempotency. A production
> producer would use a globally unique id.
