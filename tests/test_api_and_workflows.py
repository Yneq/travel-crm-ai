import os
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("SECRET_KEY", "test-secret")

from fastapi.testclient import TestClient

import dependencies
from app import app
from models.crm import QuoteStatus, TaskStatus, TravelRequestStatus, TripStatus
from models.payment import OrderStatus, PaymentStatus
from models.reminder import ReminderStatus
from models.communication import CommunicationStatus
from services.payment_provider import get_payment_provider
from services.communication_provider import get_communication_provider
from services.communication_policy import MakerCheckerConflict, ensure_independent_approver
from services.staff_policy import StaffPolicyConflict, ensure_staff_change_allowed
from services.operations_agent_graph import (
    build_action_candidates,
    run_operations_agent,
    run_operations_agent_with_fallback,
    select_tools,
)
from services.operations_agent_provider import (
    OperationsAgentProviderError,
    validate_model_answer,
)
from services.communication_templates import TemplateRenderError, render_template
from services.quote_pdf import build_quote_proposal_pdf
from services.reminder_rules import build_operational_reminder
from services.followup_provider import (
    LocalFollowUpProvider,
    PlanningProviderError,
    build_followup_prompt,
    generate_followup_with_fallback,
)
from services.ai_planning_graph import run_planning_graph
from services.planning_provider import (
    GeneratedItineraryItem,
    GeneratedTravelPlan,
    GeminiPlanningProvider,
    PlanningProviderConfigurationError,
    build_gemini_prompt,
    get_planning_provider,
)
from services.workflow import (
    InvalidTransition,
    ensure_order_transition,
    ensure_payment_transition,
    ensure_task_transition,
    ensure_travel_request_transition,
    ensure_trip_transition,
    ensure_quote_transition,
    ensure_reminder_transition,
    ensure_communication_transition,
)
from repositories.audit_repository import redact_audit_data


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.openapi = app.openapi()

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual("ok", response.json()["status"])

    def test_admin_dashboard_is_served(self):
        response = self.client.get("/admin")
        script = self.client.get("/admin-assets/admin.js")

        self.assertEqual(200, response.status_code)
        self.assertIn("VoyageOps AI", response.text)
        self.assertIn("訂單與付款", response.text)
        self.assertIn("/api/orders/", script.text)
        self.assertIn("Idempotency-Key", script.text)
        self.assertIn("營運提醒", response.text)
        self.assertIn("/api/reminders/scan", script.text)
        self.assertEqual(200, script.status_code)

    def test_crm_routes_are_exposed(self):
        expected = {
            ("/api/staff-users", "post"),
            ("/api/staff-users", "get"),
            ("/api/staff-users/{staff_id}", "patch"),
            ("/api/members", "post"),
            ("/api/members", "get"),
            ("/api/members/{member_id}", "patch"),
            ("/api/travel-requests", "post"),
            ("/api/travel-requests/{request_id}", "patch"),
            ("/api/tasks", "post"),
            ("/api/tasks/{task_id}", "patch"),
            ("/api/travel-requests/{request_id}/trips", "post"),
            ("/api/trips/{trip_id}/items", "post"),
            ("/api/trips/{trip_id}/quotes", "post"),
            ("/api/quotes/{quote_id}", "patch"),
            ("/api/quotes/{quote_id}/documents/proposal.pdf", "get"),
            ("/api/quotes/{quote_id}/orders", "post"),
            ("/api/orders", "get"),
            ("/api/orders/{order_id}/payments", "post"),
            ("/api/orders/{order_id}/payments", "get"),
            ("/api/payments/{payment_id}/simulate", "post"),
            ("/api/webhooks/payments/{provider}", "post"),
            ("/api/travel-requests/{request_id}/ai-plans", "post"),
            ("/api/travel-requests/{request_id}/ai-plans", "get"),
            ("/api/ai-plans/{run_id}", "get"),
            ("/api/ai-plans/{run_id}/review", "post"),
            ("/api/ai/providers/status", "get"),
            ("/api/reminders", "get"),
            ("/api/reminders/scan", "post"),
            ("/api/reminders/{reminder_id}", "patch"),
            ("/api/reminders/{reminder_id}/ai-draft", "post"),
            ("/api/reminders/{reminder_id}/ai-draft/review", "post"),
            ("/api/operations/jobs", "get"),
            ("/api/operations/worker/status", "get"),
            ("/api/operations/jobs/{job_id}/retry", "post"),
            ("/api/communication-drafts", "get"),
            ("/api/reminders/{reminder_id}/communication-draft", "post"),
            ("/api/communication-drafts/{draft_id}", "patch"),
            ("/api/communication-drafts/{draft_id}/approve", "post"),
            ("/api/communication-drafts/{draft_id}/send", "post"),
            ("/api/communication-templates", "get"),
            ("/api/communication-drafts/{draft_id}/versions", "get"),
            ("/api/communication-drafts/{draft_id}/templates/{template_id}", "post"),
            ("/api/audit-logs", "get"),
            ("/api/audit-logs/facets", "get"),
            ("/api/operations-agent/runs", "post"),
            ("/api/operations-agent/proposals", "get"),
            ("/api/operations-agent/proposals/{proposal_id}/review", "post"),
        }

        for path, method in expected:
            self.assertIn(path, self.openapi["paths"])
            self.assertIn(method, self.openapi["paths"][path])


class SecurityTests(unittest.TestCase):
    def test_password_is_hashed_and_verified(self):
        password_hash = dependencies.hash_password("valid-password")

        self.assertNotEqual("valid-password", password_hash)
        self.assertTrue(dependencies.verify_password("valid-password", password_hash))
        self.assertFalse(dependencies.verify_password("wrong-password", password_hash))

    def test_jwt_round_trip(self):
        dependencies.SECRET_KEY = "test-secret"
        token = dependencies.create_access_token(
            {"id": 42, "sub": "42", "role": "advisor"}
        )

        payload = dependencies.decode_access_token(token)
        self.assertEqual(42, payload["id"])
        self.assertEqual("advisor", payload["role"])

    @patch("dependencies.mysql.connector.connect")
    def test_current_user_refreshes_role_from_database(self, connect):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "email": "advisor@example.com",
            "is_active": True,
            "role": "advisor",
        }
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        token = dependencies.create_access_token(
            {"id": 42, "sub": "42", "role": "admin"}
        )

        payload = dependencies.get_current_user(
            SimpleNamespace(scheme="Bearer", credentials=token)
        )

        self.assertEqual("advisor", payload["role"])
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    @patch("dependencies.mysql.connector.connect")
    def test_inactive_user_existing_token_is_rejected(self, connect):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "email": "inactive@example.com",
            "is_active": False,
            "role": "advisor",
        }
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        token = dependencies.create_access_token(
            {"id": 42, "sub": "42", "role": "advisor"}
        )

        with self.assertRaisesRegex(Exception, "inactive"):
            dependencies.get_current_user(
                SimpleNamespace(scheme="Bearer", credentials=token)
            )


class StaffPolicyTests(unittest.TestCase):
    def test_admin_cannot_change_own_access(self):
        with self.assertRaises(StaffPolicyConflict):
            ensure_staff_change_allowed(
                actor_id=1, target_id=1, current_role="admin",
                current_active=True, next_role="advisor", next_active=True,
                active_admin_count=2,
            )

    def test_last_active_admin_cannot_be_removed(self):
        with self.assertRaises(StaffPolicyConflict):
            ensure_staff_change_allowed(
                actor_id=2, target_id=1, current_role="admin",
                current_active=True, next_role="admin", next_active=False,
                active_admin_count=1,
            )

    def test_another_staff_member_can_be_updated(self):
        ensure_staff_change_allowed(
            actor_id=1, target_id=2, current_role="advisor",
            current_active=True, next_role="finance", next_active=True,
            active_admin_count=1,
        )

    def test_audit_output_redacts_nested_credentials(self):
        data = redact_audit_data({
            "email": "allowed@example.com",
            "auth": {"access_token": "secret-token", "items": [{"api_key": "key"}]},
        })

        self.assertEqual("allowed@example.com", data["email"])
        self.assertEqual("[REDACTED]", data["auth"]["access_token"])
        self.assertEqual("[REDACTED]", data["auth"]["items"][0]["api_key"])


class OperationsAgentTests(unittest.TestCase):
    def test_write_intent_creates_task_proposal_without_executing(self):
        candidates = build_action_candidates(
            "替未付款訂單建立跟進任務",
            [{
                "tool": "payment_followups",
                "result": {"items": [{
                    "id": 7, "member_id": 3, "order_number": "ORD-007",
                    "member_name": "Regression Member",
                }]},
            }],
            now=datetime(2026, 9, 7),
        )

        self.assertEqual(1, len(candidates))
        self.assertEqual("create_task", candidates[0]["action_type"])
        self.assertEqual(7, candidates[0]["action_payload"]["source_id"])
        self.assertNotIn("payment", candidates[0]["action_type"])

    def test_read_question_does_not_create_write_proposal(self):
        self.assertEqual([], build_action_candidates("有哪些未付款訂單？", []))

    def test_question_selects_multiple_relevant_tools(self):
        self.assertEqual(
            ["overdue_tasks", "payment_followups"],
            select_tools("今天有哪些逾期任務和未付款訂單？"),
        )

    def test_unknown_question_falls_back_to_overview(self):
        self.assertEqual(["operations_overview"], select_tools("目前狀況如何？"))

    def test_graph_executes_read_tools_and_applies_guardrail(self):
        calls = []

        def execute(tool):
            calls.append(tool)
            return {
                "summary": {
                    "active_members": 3,
                    "active_requests": 2,
                    "open_tasks": 1,
                    "pending_payments": 1,
                    "scheduled_reminders": 4,
                },
                "items": [],
            }

        result = run_operations_agent("給我營運總覽", execute)

        self.assertEqual(["operations_overview"], calls)
        self.assertTrue(result["guardrails"]["read_only_tools"])
        self.assertFalse(result["guardrails"]["external_actions_executed"])
        self.assertIn("tool:operations_overview", result["node_trace"])

    def test_model_provider_tool_calls_are_exposed(self):
        provider = MagicMock()
        provider.run.return_value = {
            "answer": "目前有一筆待付款訂單，請由人員確認。",
            "tool_results": [
                {"tool": "payment_followups", "result": {"items": [{"id": 9}]}}
            ],
            "provider": "gemini:test-model",
        }

        result = run_operations_agent_with_fallback(
            "有哪些待付款？", lambda _tool: {}, "gemini", provider=provider
        )

        self.assertEqual("gemini:test-model", result["provider"])
        self.assertFalse(result["fallback_used"])
        self.assertEqual("payment_followups", result["tools_used"][0]["tool"])

    def test_model_failure_uses_deterministic_fallback(self):
        provider = MagicMock()
        provider.run.side_effect = OperationsAgentProviderError("offline")

        result = run_operations_agent_with_fallback(
            "給我營運總覽",
            lambda _tool: {"summary": {
                "active_members": 0, "active_requests": 0, "open_tasks": 0,
                "pending_payments": 0, "scheduled_reminders": 0,
            }, "items": []},
            "gemini",
            provider=provider,
        )

        self.assertEqual("langgraph-local", result["provider"])
        self.assertTrue(result["fallback_used"])

    def test_unsafe_model_action_claim_is_rejected(self):
        with self.assertRaises(OperationsAgentProviderError):
            validate_model_answer("已替你付款，訂單處理完成。")
        with self.assertRaises(OperationsAgentProviderError):
            validate_model_answer("已建立任務並安排同仁跟進。")


class WorkflowTests(unittest.TestCase):
    def test_valid_travel_request_transition(self):
        ensure_travel_request_transition("new", TravelRequestStatus.QUALIFIED)

    def test_invalid_travel_request_transition(self):
        with self.assertRaises(InvalidTransition):
            ensure_travel_request_transition("new", TravelRequestStatus.BOOKED)

    def test_completed_task_can_be_reopened(self):
        ensure_task_transition("completed", TaskStatus.OPEN)

    def test_trip_requires_review_before_confirmation(self):
        with self.assertRaises(InvalidTransition):
            ensure_trip_transition("draft", TripStatus.CONFIRMED)
        ensure_trip_transition("draft", TripStatus.REVIEW)
        ensure_trip_transition("review", TripStatus.CONFIRMED)

    def test_quote_requires_pending_approval(self):
        with self.assertRaises(InvalidTransition):
            ensure_quote_transition("draft", QuoteStatus.APPROVED)
        ensure_quote_transition("draft", QuoteStatus.PENDING_APPROVAL)
        ensure_quote_transition("pending_approval", QuoteStatus.APPROVED)

    def test_order_is_paid_before_fulfillment(self):
        with self.assertRaises(InvalidTransition):
            ensure_order_transition("pending_payment", OrderStatus.FULFILLED)
        ensure_order_transition("pending_payment", OrderStatus.PAID)
        ensure_order_transition("paid", OrderStatus.FULFILLED)

    def test_payment_result_is_terminal(self):
        ensure_payment_transition("processing", PaymentStatus.SUCCEEDED)
        ensure_payment_transition("processing", PaymentStatus.FAILED)
        with self.assertRaises(InvalidTransition):
            ensure_payment_transition("failed", PaymentStatus.SUCCEEDED)

    def test_reminder_review_is_terminal(self):
        ensure_reminder_transition("scheduled", ReminderStatus.ACKNOWLEDGED)
        ensure_reminder_transition("scheduled", ReminderStatus.DISMISSED)
        with self.assertRaises(InvalidTransition):
            ensure_reminder_transition("acknowledged", ReminderStatus.DISMISSED)

    def test_communication_requires_approval_before_send(self):
        ensure_communication_transition("draft", CommunicationStatus.APPROVED)
        ensure_communication_transition("approved", CommunicationStatus.SENT)
        with self.assertRaises(InvalidTransition):
            ensure_communication_transition("draft", CommunicationStatus.SENT)
        with self.assertRaises(InvalidTransition):
            ensure_communication_transition("sent", CommunicationStatus.DRAFT)

    def test_communication_maker_cannot_approve_own_edit(self):
        with self.assertRaises(MakerCheckerConflict):
            ensure_independent_approver(actor_id=7, last_edited_by=7)

    def test_communication_checker_must_be_a_different_user(self):
        ensure_independent_approver(actor_id=8, last_edited_by=7)


class ReminderRuleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 5, 12, 0, 0)

    def test_overdue_task_becomes_urgent_internal_reminder(self):
        reminder = build_operational_reminder({
            "signal_type": "task_due", "source_id": 7, "member_id": 3,
            "title": "確認機票", "due_at": self.now - timedelta(hours=2),
        }, self.now)

        self.assertEqual("urgent", reminder["payload"]["severity"])
        self.assertEqual("逾期：確認機票", reminder["title"])
        self.assertEqual("task_due:7:2026-09-05T10:00:00", reminder["dedup_key"])

    def test_pending_payment_requires_human_follow_up(self):
        reminder = build_operational_reminder({
            "signal_type": "payment_follow_up", "source_id": 9, "member_id": 3,
            "order_number": "ORD-009", "total": Decimal("52000"), "currency": "TWD",
            "created_at": self.now - timedelta(hours=25),
        }, self.now)

        self.assertEqual("payment_follow_up", reminder["reminder_type"])
        self.assertIn("再決定是否聯絡旅客", reminder["payload"]["recommended_action"])
        self.assertEqual("payment_follow_up:9:2026-09-04", reminder["dedup_key"])


class FollowUpCopilotTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "member": {
                "name": "Demo Traveler", "tier": "vip", "locale": "zh-TW",
                "email": "private@example.com", "phone": "0900000000",
            },
            "reminder": {
                "type": "payment_follow_up", "title": "待付款訂單：ORD-009",
                "reason": "訂單建立超過 24 小時仍未完成付款",
                "recommended_action": "由顧問確認付款狀態", "severity": "high",
            },
        }

    def test_local_followup_is_a_human_reviewed_draft(self):
        draft = LocalFollowUpProvider().generate_followup(self.context)

        self.assertTrue(draft["requires_human_review"])
        self.assertIn("付款狀態確認", draft["message_subject"])
        self.assertIn("由顧問", draft["recommended_steps"][-1])

    def test_followup_prompt_excludes_contact_details(self):
        prompt = build_followup_prompt(self.context)

        self.assertIn("Demo Traveler", prompt)
        self.assertNotIn("private@example.com", prompt)
        self.assertNotIn("0900000000", prompt)

    @patch("services.followup_provider.get_followup_provider")
    def test_external_failure_falls_back_to_safe_local_draft(self, provider_factory):
        failing_provider = MagicMock()
        failing_provider.generate_followup.side_effect = PlanningProviderError("temporary")
        provider_factory.return_value = failing_provider

        draft, provider_name = generate_followup_with_fallback(self.context, "gemini")

        self.assertEqual("local-followup:fallback", provider_name)
        self.assertTrue(draft["requires_human_review"])
        self.assertIn("本機安全草稿", draft["provider_warning"])


class PaymentProviderTests(unittest.TestCase):
    def test_mockpay_returns_processing_attempt_with_traceable_payload(self):
        provider = get_payment_provider("mockpay")

        result = provider.initiate(1500, "TWD", "payment-request-123")

        self.assertTrue(result.provider_transaction_id.startswith("mock_"))
        self.assertEqual("processing", result.status)
        self.assertEqual("payment-request-123", result.provider_payload["idempotency_key"])

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            get_payment_provider("unknown")

    def test_mock_email_never_uses_network_delivery(self):
        delivery = get_communication_provider("mock-email").send(
            "Demo Traveler", "行程確認", "這是本機測試草稿"
        )

        self.assertTrue(delivery.provider_message_id.startswith("mock_msg_"))
        self.assertFalse(delivery.payload["network_delivery"])
        self.assertEqual("local-simulation", delivery.payload["mode"])


class CommunicationTemplateTests(unittest.TestCase):
    def test_allowed_placeholders_are_rendered(self):
        rendered = render_template(
            "{{member_name}}：{{reminder_title}}",
            {"member_name": "Demo Traveler", "reminder_title": "行程確認"},
        )

        self.assertEqual("Demo Traveler：行程確認", rendered)

    def test_unknown_placeholder_is_rejected(self):
        with self.assertRaises(TemplateRenderError):
            render_template("{{email}}", {"email": "private@example.com"})

    def test_missing_allowed_value_is_rejected(self):
        with self.assertRaises(TemplateRenderError):
            render_template("{{member_name}}：{{recommended_action}}", {"member_name": "Demo"})


class QuotePdfTests(unittest.TestCase):
    def test_quote_snapshot_renders_as_pdf(self):
        content = build_quote_proposal_pdf({
            "quote_number": "Q-000003-V01",
            "version": 1,
            "status": "approved",
            "currency": "TWD",
            "member_name": "示範旅客",
            "destination": "東京",
            "trip_name": "東京五日高端行程",
            "start_date": date(2026, 10, 1),
            "end_date": date(2026, 10, 5),
            "party_size": 2,
            "subtotal": Decimal("250000"),
            "tax": Decimal("12500"),
            "total": Decimal("262500"),
            "expires_at": date(2026, 9, 30),
            "notes": "顧問核准後提供",
            "items": [{
                "title": "機場接送與入住",
                "item_type": "transfer",
                "unit_price": Decimal("20000"),
                "quantity": 1,
                "line_total": Decimal("20000"),
            }],
        })

        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 2000)


class AIPlanningGraphTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "request": {
                "destination": "Tokyo",
                "party_size": 2,
                "budget_currency": "TWD",
                "budget_amount": 120000,
                "start_date": date(2026, 10, 1),
                "end_date": date(2026, 10, 3),
                "requirements": {"notes": "family trip"},
                "version": 1,
            },
            "member": {"name": "Demo Member"},
            "preferences": {"travel_styles": ["luxury", "family"]},
        }

    def test_graph_executes_all_planning_and_guardrail_nodes(self):
        result = run_planning_graph(
            self.context, "需要親子友善安排", get_planning_provider("local")
        )

        self.assertEqual(
            [
                "prepare_privacy_safe_context",
                "identify_missing_information",
                "generate_structured_plan",
                "quality_guardrail",
            ],
            result["node_trace"],
        )
        self.assertTrue(result["guardrails"]["requires_human_review"])
        self.assertFalse(result["guardrails"]["unverified_prices"])
        self.assertGreaterEqual(len(result["itinerary_items"]), 3)

    def test_graph_reports_missing_request_information(self):
        self.context["request"]["budget_amount"] = None
        self.context["request"]["requirements"] = {}

        result = run_planning_graph(self.context, None, get_planning_provider())

        self.assertIn("budget_amount", result["missing_fields"])
        self.assertIn("requirements", result["missing_fields"])

    def test_gemini_prompt_uses_privacy_allowlist(self):
        self.context["member"].update({"email": "private@example.com", "phone": "0900000000"})

        prompt = build_gemini_prompt(self.context, "slow pace")

        self.assertNotIn("private@example.com", prompt)
        self.assertNotIn("0900000000", prompt)
        self.assertIn("slow pace", prompt)

    def test_gemini_provider_requires_an_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PlanningProviderConfigurationError):
                get_planning_provider("gemini")

    def test_gemini_provider_requests_one_structured_response(self):
        generated = GeneratedTravelPlan(
            summary="結構化摘要",
            itinerary_items=[
                GeneratedItineraryItem(
                    day=1,
                    item_type="transfer",
                    title="抵達與接送",
                    location="Tokyo",
                    rationale="需確認航班時間。",
                ),
                GeneratedItineraryItem(
                    day=2,
                    item_type="activity",
                    title="文化體驗",
                    location="Tokyo",
                    rationale="需確認營業時間。",
                ),
            ],
        )
        generate_content = MagicMock(return_value=SimpleNamespace(parsed=generated, text=None))
        fake_client = MagicMock()
        fake_client.__enter__.return_value.models.generate_content = generate_content
        provider = GeminiPlanningProvider("test-key", "gemini-3.8-flash")

        with patch("google.genai.Client", return_value=fake_client):
            result = provider.generate_plan(self.context, None)

        self.assertEqual("結構化摘要", result["summary"])
        generate_content.assert_called_once()

    def test_gemini_provider_retries_transient_server_error(self):
        from google.genai import errors

        generated = GeneratedTravelPlan(
            summary="重試後成功",
            itinerary_items=[
                GeneratedItineraryItem(
                    day=1,
                    item_type="transfer",
                    title="接送",
                    rationale="需確認時間。",
                ),
                GeneratedItineraryItem(
                    day=2,
                    item_type="activity",
                    title="活動",
                    rationale="需確認預約狀態。",
                ),
            ],
        )
        generate_content = MagicMock(
            side_effect=[
                errors.ServerError(
                    503,
                    {"error": {"message": "high demand", "status": "UNAVAILABLE"}},
                ),
                SimpleNamespace(parsed=generated, text=None),
            ]
        )
        fake_client = MagicMock()
        fake_client.__enter__.return_value.models.generate_content = generate_content
        provider = GeminiPlanningProvider(
            "test-key", "gemini-3.8-flash", max_retries=2
        )

        with (
            patch("google.genai.Client", return_value=fake_client),
            patch("services.planning_provider.time.sleep") as sleep,
        ):
            result = provider.generate_plan(self.context, None)

        self.assertEqual("重試後成功", result["summary"])
        self.assertEqual(2, generate_content.call_count)
        sleep.assert_called_once_with(1)

    def test_gemini_provider_falls_back_after_transient_retries(self):
        from google.genai import errors

        generated = GeneratedTravelPlan(
            summary="fallback success",
            itinerary_items=[
                GeneratedItineraryItem(
                    day=1, item_type="hotel", title="Hotel", rationale="Verify."
                ),
                GeneratedItineraryItem(
                    day=2, item_type="activity", title="Tour", rationale="Verify."
                ),
            ],
        )
        unavailable = errors.ServerError(
            503,
            {"error": {"message": "high demand", "status": "UNAVAILABLE"}},
        )
        generate_content = MagicMock(
            side_effect=[
                unavailable,
                unavailable,
                unavailable,
                SimpleNamespace(parsed=generated, text=None),
            ]
        )
        fake_client = MagicMock()
        fake_client.__enter__.return_value.models.generate_content = generate_content
        provider = GeminiPlanningProvider(
            "test-key",
            "gemini-3.8-flash",
            max_retries=2,
            fallback_model="gemini-3.5-flash-lite",
        )

        with (
            patch("google.genai.Client", return_value=fake_client),
            patch("services.planning_provider.time.sleep") as sleep,
        ):
            result = provider.generate_plan(self.context, None)

        self.assertEqual("fallback success", result["summary"])
        self.assertEqual("gemini:gemini-3.5-flash-lite", provider.name)
        self.assertEqual(4, generate_content.call_count)
        self.assertEqual([((1,),), ((2,),)], sleep.call_args_list)

    def test_gemini_provider_falls_back_when_structured_output_is_invalid(self):
        generated = GeneratedTravelPlan(
            summary="valid fallback",
            itinerary_items=[
                GeneratedItineraryItem(
                    day=1, item_type="hotel", title="Hotel", rationale="Verify."
                ),
                GeneratedItineraryItem(
                    day=2, item_type="activity", title="Tour", rationale="Verify."
                ),
            ],
        )
        generate_content = MagicMock(
            side_effect=[
                SimpleNamespace(parsed=None, text="{invalid"),
                SimpleNamespace(parsed=generated, text=None),
            ]
        )
        fake_client = MagicMock()
        fake_client.__enter__.return_value.models.generate_content = generate_content
        provider = GeminiPlanningProvider(
            "test-key",
            "gemini-3.8-flash",
            fallback_model="gemini-3.5-flash-lite",
        )

        with patch("google.genai.Client", return_value=fake_client):
            result = provider.generate_plan(self.context, None)

        self.assertEqual("valid fallback", result["summary"])
        self.assertEqual("gemini:gemini-3.5-flash-lite", provider.name)
        self.assertEqual(2, generate_content.call_count)


if __name__ == "__main__":
    unittest.main()
