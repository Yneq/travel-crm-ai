from datetime import datetime, timezone


QUEUE_KEY = "voyageops:jobs:scheduled"


class RedisJobQueue:
    POP_DUE_SCRIPT = """
    local item = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)
    if #item == 0 then return nil end
    if redis.call('ZREM', KEYS[1], item[1]) == 1 then return item[1] end
    return nil
    """

    def __init__(self, client):
        self.client = client

    def schedule(self, job_id: int, run_at: datetime) -> None:
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        self.client.zadd(QUEUE_KEY, {str(job_id): run_at.timestamp()})

    def pop_due(self, now: datetime) -> int | None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        result = self.client.eval(self.POP_DUE_SCRIPT, 1, QUEUE_KEY, now.timestamp())
        return int(result) if result is not None else None

    def ping(self) -> bool:
        return bool(self.client.ping())
