"""Exit successfully only when the worker's two dependencies respond."""

import os

import mysql.connector
import redis


connection = mysql.connector.connect(
    host=os.environ["RDS_HOST"],
    user=os.environ["DB_USER"],
    password=os.environ["RDS_PASSWORD"],
    database=os.environ["DB_NAME"],
    connection_timeout=2,
)
try:
    cursor = connection.cursor()
    cursor.execute("SELECT 1 FROM integration_events LIMIT 1")
    cursor.fetchone()
    cursor.close()
finally:
    connection.close()

client = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ.get("REDIS_PORT", "6379")),
    socket_timeout=2,
)
try:
    if not client.ping():
        raise RuntimeError("Redis did not respond to PING")
finally:
    client.close()
