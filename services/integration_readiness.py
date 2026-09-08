import os


def integration_status() -> dict:
    payment_mode = os.getenv("PAYMENT_PROVIDER", "mockpay")
    email_mode = os.getenv("EMAIL_PROVIDER", "mock-email")
    ai_mode = os.getenv("AI_OPERATIONS_PROVIDER", "local")
    gemini_configured = bool(os.getenv("GEMINI_API_KEY"))
    components = [
        {
            "component": "payment",
            "mode": payment_mode,
            "configured": payment_mode == "mockpay",
            "external_actions_enabled": False,
            "note": "MockPay only; production provider adapter is intentionally fail-closed.",
        },
        {
            "component": "email",
            "mode": email_mode,
            "configured": email_mode == "mock-email",
            "external_actions_enabled": False,
            "note": "Mock Email only; no external message delivery is enabled.",
        },
        {
            "component": "operations_ai",
            "mode": ai_mode,
            "configured": ai_mode == "local" or gemini_configured,
            "external_actions_enabled": False,
            "note": "AI tools remain read-only; CRM writes require human approval.",
        },
    ]
    return {
        "production_ready": all(
            component["configured"] and component["external_actions_enabled"]
            for component in components[:2]
        ),
        "components": components,
    }
