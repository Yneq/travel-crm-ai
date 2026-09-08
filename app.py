import os
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from dependencies import get_db
from services.observability import log_request, request_metrics

from controllers import (
    ai_controller,
    audit_controller,
    communication_controller,
    crm_controller,
    operations_controller,
    operations_agent_controller,
    payment_controller,
    reminder_controller,
    trip_controller,
    user_controller,
)


app = FastAPI(
    title="VoyageOps AI API",
    version="0.1.0",
    description="AI-assisted travel CRM and operations platform",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8080",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@app.middleware("http")
async def observe_requests(request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = perf_counter() - started
        route = getattr(request.scope.get("route"), "path", request.url.path)
        request_metrics.record(request.method, route, 500, duration)
        log_request({
            "request_id": request_id, "method": request.method, "route": route,
            "status": 500, "duration_ms": round(duration * 1000, 2),
        })
        raise
    duration = perf_counter() - started
    route = getattr(request.scope.get("route"), "path", request.url.path)
    request_metrics.record(request.method, route, response.status_code, duration)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration * 1000:.2f}"
    log_request({
        "request_id": request_id, "method": request.method, "route": route,
        "status": response.status_code, "duration_ms": round(duration * 1000, 2),
    })
    return response

app.mount("/admin-assets", StaticFiles(directory="admin"), name="admin-assets")


@app.get("/", include_in_schema=False)
def application_home():
    return RedirectResponse(url="/admin")


@app.get("/admin", include_in_schema=False)
def admin_dashboard():
    return FileResponse("admin/index.html")


@app.get("/health", tags=["operations"])
def health_check():
    return {"status": "ok", "service": "voyageops-api"}


@app.get("/health/live", tags=["operations"])
def liveness_check():
    return {"status": "ok", "service": "voyageops-api"}


@app.get("/health/ready", tags=["operations"])
def readiness_check():
    components = {"mysql": False, "redis": False}
    connection = None
    cursor = None
    try:
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        components["mysql"] = True
    except Exception:
        pass
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    client = None
    try:
        import redis

        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            socket_timeout=1,
        )
        components["redis"] = bool(client.ping())
    except Exception:
        pass
    finally:
        if client is not None:
            client.close()
    ready = all(components.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "components": components},
    )


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return PlainTextResponse(
        request_metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


app.include_router(user_controller.router)
app.include_router(crm_controller.router)
app.include_router(trip_controller.router)
app.include_router(payment_controller.router)
app.include_router(ai_controller.router)
app.include_router(reminder_controller.router)
app.include_router(operations_controller.router)
app.include_router(operations_agent_controller.router)
app.include_router(communication_controller.router)
app.include_router(audit_controller.router)
