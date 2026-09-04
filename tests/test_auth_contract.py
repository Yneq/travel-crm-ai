import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _routes():
    tree = ast.parse((ROOT / "controllers" / "user_controller.py").read_text())
    routes = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or not decorator.args:
                continue
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str):
                routes.add((func.attr.upper(), path.value))
    return routes


class AuthenticationContractTests(unittest.TestCase):
    def test_authentication_routes_use_resource_oriented_contracts(self):
        routes = _routes()

        self.assertIn(("POST", "/api/auth/register"), routes)
        self.assertIn(("POST", "/api/auth/login"), routes)
        self.assertIn(("GET", "/api/users/me"), routes)
        self.assertNotIn(("PUT", "/api/user/auth"), routes)

    def test_frontend_uses_v2_authentication_contract(self):
        script = (ROOT / "static" / "scripts.js").read_text()

        self.assertIn("fetch('/api/auth/login'", script)
        self.assertIn("fetch('/api/auth/register'", script)
        self.assertIn("fetch('/api/users/me'", script)
        self.assertNotIn("fetch('/api/user/auth'", script)


if __name__ == "__main__":
    unittest.main()
