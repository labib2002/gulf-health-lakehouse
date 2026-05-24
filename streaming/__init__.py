"""Kafka streaming demo: producer -> topic -> consumer -> Postgres."""

TOPIC = "wearable-events"
NUM_PARTITIONS = 3
CONSUMER_GROUP = "wearable-loaders"
