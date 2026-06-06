# ADR 0007 — Streaming with Kafka

- **Status:** Accepted
- **Phase:** 6 — Kafka
- **Date:** 2026-06-05

## Context

We want to show a real streaming path for wearable events — produce in real time,
land via a consumer — with **deliberate topic design** (partitions, keys,
consumer groups), `acks=all`, and offset handling. Scope is intentionally
**producer/consumer + topic design, not cluster operations**.

## Decision

- **Single-broker Kafka in KRaft mode** (`confluentinc/cp-kafka`, no ZooKeeper),
  `streaming/docker-compose.kafka.yml`, joined to the shared `health-net` so the
  consumer reaches the data Postgres. Internal (`29092`) and external (`9092`)
  listeners so producer/consumer can run from the host.
- **Topic `wearable-events`, 3 partitions, replication 1** (single broker),
  created deliberately (`auto.create.topics=false`).
- **Producer** (`producer.py`): streams synthetic HR/steps events **keyed by
  `user_id`** with **`acks=all`** + idempotence. Keying puts all of a user's
  events on one partition → per-user ordering.
- **Consumer** (`consumer.py`): member of the **`wearable-loaders` group**,
  auto-commit **off**; it inserts a row then **commits the offset** → at-least-
  once. The Postgres table has a unique `event_id` and the write is an upsert, so
  reprocessing is idempotent (no duplicates).
- A **mermaid topology** lives in `docs/kafka_topology.md`.

## Verified locally

- 500 events produced (acks=all) → consumed → `streaming.wearable_events`.
- Spread across all 3 partitions (155/172/173); **0 users span >1 partition**
  (key ordering holds).
- Two consumers in the group split 600 events 186/414 (2-vs-1 partition
  assignment) — demonstrates group scaling/rebalancing.
- Re-running the producer (same per-run sequential ids) deduped via the upsert —
  demonstrates the idempotent at-least-once write.

## Alternatives considered

- **ZooKeeper-based Kafka** — rejected; KRaft is the modern, simpler single-binary
  mode and avoids running a second service.
- **More partitions / multiple brokers** — out of scope; the brief says topic
  design, not cluster ops. 3 partitions is enough to show keying + group sharing.
- **Auto-create topics** — rejected; deliberate creation makes partition count an
  explicit design choice.
- **Consume straight to BigQuery** — Postgres keeps the demo self-contained and
  reuses the existing engine; the same consumer pattern applies to any sink.

## Consequences

- A faithful, runnable streaming demo without cluster-ops complexity.
- The consumer's commit-after-write pattern is the at-least-once template; exactly
  -once would need transactional produce+consume (noted, not implemented).

## Interview check

**What does `acks=all` mean?**
The producer waits for the leader **and all in-sync replicas (ISR)** to
acknowledge a write before considering it successful. It's the strongest
durability setting — no acknowledged message is lost if the leader fails (a
replica has it). `acks=1` waits only for the leader (can lose data on leader
failure); `acks=0` doesn't wait at all. (With a single broker here ISR is just the
leader, but the setting is the production-correct choice.)

**What happens when a consumer in a group dies?**
Kafka triggers a **rebalance**: the dead consumer's partitions are reassigned to
the surviving members of the group, so consumption continues. Because we commit
offsets only after the DB write, the new owner resumes from the last committed
offset and reprocesses at most the in-flight batch (at-least-once) — the upsert
makes that safe.

**When would you NOT use Kafka?**
When you don't have a streaming/decoupling need: simple request/response, low
event volume, or a periodic batch that a scheduled job (Airflow) handles fine.
Kafka adds real operational weight (brokers, partitions, consumer-group
semantics, offset management); for small or purely batch workloads it's
over-engineering. It shines for high-throughput, multi-consumer, replayable event
streams — not as a general-purpose queue or database.
