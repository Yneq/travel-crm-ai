"""Separate observed model behavior from system fallback/transport behavior."""
from collections import Counter


def analyze_run(run):
    cases = [case for workflow in run['workflows'].values() for case in workflow['cases']]
    provider, model = run['provider_requested'], run['model_requested']
    def matched(case):
        actual = case.get('provider') or ''
        return (actual == provider or actual.startswith(provider + ':') or
                (provider == 'local' and (actual.startswith('local-') or actual == 'langgraph-local'))) and case.get('model') == model
    observed = [case for case in cases if matched(case) and not case.get('fallback_used')]
    tools = [case for case in observed if case.get('tool_selection_pass') is not None]
    errors = Counter()
    for case in cases:
        error = case.get('provider_error') or case.get('error')
        if error:
            errors[error.split(':', 1)[0]] += 1
    return {'case_count': len(cases), 'matched_provider_case_count': len(observed),
            'fallback_case_count': sum(bool(c.get('fallback_used')) for c in cases),
            'observed_tool_case_count': len(tools),
            'observed_tool_selection_accuracy': sum(bool(c['tool_selection_pass']) for c in tools) / len(tools) if tools else None,
            'errors_by_type': dict(errors),
            'limitations': ['Observed tool accuracy excludes fallback and unavailable model responses; always report observed case count with the rate.',
                            'An exception before structured validation may leave actual model identity unavailable even if the server generated tokens.']}
