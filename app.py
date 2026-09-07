import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from controllers import (
    ai_controller,
    communication_controller,
    crm_controller,
    operations_controller,
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


app.include_router(user_controller.router)
app.include_router(crm_controller.router)
app.include_router(trip_controller.router)
app.include_router(payment_controller.router)
app.include_router(ai_controller.router)
app.include_router(reminder_controller.router)
app.include_router(operations_controller.router)
app.include_router(communication_controller.router)
