import json
import logging
from collections import defaultdict
from threading import Lock


logger = logging.getLogger("voyageops.requests")


class RequestMetrics:
    def __init__(self):
        self._lock = Lock()
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(float)

    def record(self, method: str, route: str, status: int, duration_seconds: float) -> None:
        with self._lock:
            self._counts[(method, route, status)] += 1
            self._duration_seconds[(method, route)] += duration_seconds

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP voyageops_http_requests_total Total HTTP requests.",
                "# TYPE voyageops_http_requests_total counter",
            ]
            for (method, route, status), count in sorted(self._counts.items()):
                lines.append(
                    f'voyageops_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}'
                )
            lines.extend([
                "# HELP voyageops_http_request_duration_seconds_total Cumulative HTTP request duration.",
                "# TYPE voyageops_http_request_duration_seconds_total counter",
            ])
            for (method, route), duration in sorted(self._duration_seconds.items()):
                lines.append(
                    f'voyageops_http_request_duration_seconds_total{{method="{method}",route="{route}"}} {duration:.6f}'
                )
            return "\n".join(lines) + "\n"


request_metrics = RequestMetrics()


def log_request(event: dict) -> None:
    logger.info(json.dumps(event, ensure_ascii=False, default=str))
