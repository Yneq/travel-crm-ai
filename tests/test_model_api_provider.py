import unittest
from unittest.mock import patch
import httpx
from services.benchmark_provider import BenchmarkTarget, make_benchmark_adapter
from services.model_api_provider import ModelApiFollowUpProvider
from model_service.app import GenerationRequest
from pydantic import ValidationError


class ModelApiContractTests(unittest.TestCase):
    def test_default_target_uses_independent_api(self):
        target = BenchmarkTarget("model-api")
        self.assertEqual(target.model, "Qwen/Qwen2.5-0.5B-Instruct")
        self.assertIsInstance(make_benchmark_adapter(target).followup(), ModelApiFollowUpProvider)

    def response(self, **overrides):
        data = {"provider": "model-api", "model": "test-model", "text": "{}",
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
        data.update(overrides)
        return httpx.Response(200, json=data, request=httpx.Request("POST", "http://model/v1/generate"))

    def test_repair_usage_accumulates_and_identity_is_checked(self):
        provider = ModelApiFollowUpProvider("test-model")
        with patch("services.model_api_provider.httpx.post", return_value=self.response()):
            provider.generate("first")
            provider.generate("repair")
        self.assertEqual(provider.last_usage.total_token_count, 24)
        with patch("services.model_api_provider.httpx.post", return_value=self.response(model="wrong")):
            with self.assertRaises(ValueError):
                provider.generate("first")

    def test_missing_usage_is_unavailable_and_request_is_bounded(self):
        provider = ModelApiFollowUpProvider("test-model")
        with patch("services.model_api_provider.httpx.post", return_value=self.response(usage=None)):
            provider.generate("first")
        self.assertIsNone(provider.last_usage)
        with self.assertRaises(ValidationError):
            GenerationRequest(model="x", instruction="hello", max_tokens=1025)

    def test_crm_factories_select_api_without_changing_local_defaults(self):
        from services.planning_provider import get_planning_provider
        from services.followup_provider import get_followup_provider
        from services.operations_agent_provider import get_operations_agent_provider
        for factory in (get_planning_provider, get_followup_provider, get_operations_agent_provider):
            self.assertEqual(factory('model-api', model='test-model').name, 'model-api:test-model')
        self.assertEqual(get_planning_provider().name, 'local-planner')

    def test_followup_api_timeout_uses_existing_safe_fallback(self):
        import json
        from pathlib import Path
        from services.followup_provider import generate_followup_with_fallback
        context = json.loads(Path('evals/fixtures.json').read_text())['followup'][0]['context']
        with patch('services.model_api_provider.httpx.post', side_effect=httpx.ReadTimeout('timeout')):
            result, provider = generate_followup_with_fallback(context, 'model-api')
        self.assertTrue(provider.endswith(':fallback'))
        self.assertTrue(result['requires_human_review'])
        self.assertIn('provider_warning', result)

    def test_operations_factory_is_used_for_explicit_api_target(self):
        from unittest.mock import Mock
        from services.operations_agent_graph import run_operations_agent_with_fallback
        provider = Mock()
        provider.run.side_effect = RuntimeError('service unavailable')
        with patch('services.operations_agent_graph.get_operations_agent_provider', return_value=provider) as factory:
            result = run_operations_agent_with_fallback('營運總覽', lambda name: {'summary': {
                'active_members': 0, 'active_requests': 0, 'open_tasks': 0,
                'pending_payments': 0, 'scheduled_reminders': 0}}, 'model-api')
        factory.assert_called_once_with('model-api')
        self.assertTrue(result['fallback_used'])
        self.assertFalse(result['guardrails']['external_actions_executed'])
