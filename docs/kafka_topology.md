# Kafka topology

Topic `wearable-events`, 3 partitions, keyed by `user_id`, consumed by the
`wearable-loaders` group landing into Postgres. See
[ADR-0007](adr/0007-kafka.md).

```mermaid
flowchart LR
  subgraph Producers
    P[producer.py<br/>key=user_id, acks=all]
  end

  subgraph "Topic: wearable-events"
    T0[(partition 0)]
    T1[(partition 1)]
    T2[(partition 2)]
  end

  subgraph "Consumer group: wearable-loaders"
    C1[consumer A]
    C2[consumer B]
  end

  PG[(Postgres<br/>streaming.wearable_events)]

  P -->|hash user_id| T0
  P -->|hash user_id| T1
  P -->|hash user_id| T2

  T0 --> C1
  T1 --> C1
  T2 --> C2

  C1 --> PG
  C2 --> PG
```

- **Keying by `user_id`** → all of a user's events hash to the **same partition**
  → per-user ordering is preserved (verified: 0 users span >1 partition).
- **3 partitions** → the group scales to up to 3 parallel consumers; with 2
  consumers Kafka assigns 2 partitions to one and 1 to the other (verified split).
- **Group rebalancing**: when a consumer joins/leaves, Kafka reassigns partitions
  across the surviving members.
