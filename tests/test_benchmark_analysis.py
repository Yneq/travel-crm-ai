import unittest
from services.benchmark_analysis import analyze_run


class ProviderObservationTests(unittest.TestCase):
    def test_fallback_tools_are_not_credited_to_model(self):
        run = {'provider_requested': 'model-api', 'model_requested': 'qwen',
               'workflows': {'operations': {'cases': [
                   {'provider': 'local-operations-agent', 'model': None,
                    'fallback_used': True, 'tool_selection_pass': True},
                   {'provider': 'model-api:qwen', 'model': 'qwen',
                    'fallback_used': False, 'tool_selection_pass': False},
               ]}}}
        result = analyze_run(run)
        self.assertEqual(result['fallback_case_count'], 1)
        self.assertEqual(result['observed_tool_case_count'], 1)
        self.assertEqual(result['observed_tool_selection_accuracy'], 0)
        run['workflows']['operations']['cases'].pop()
        result = analyze_run(run)
        self.assertEqual(result['observed_tool_case_count'], 0)
        self.assertIsNone(result['observed_tool_selection_accuracy'])

    def test_local_graph_is_a_real_baseline_observation(self):
        result = analyze_run({"provider_requested": "local", "model_requested": None,
                              "workflows": {"operations": {"cases": [
                                  {"provider": "langgraph-local", "model": None,
                                   "fallback_used": False, "tool_selection_pass": True}]}}})
        self.assertEqual(result["observed_tool_case_count"], 1)
        self.assertEqual(result["observed_tool_selection_accuracy"], 1)
