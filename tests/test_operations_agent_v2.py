import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from repositories.operations_agent_repository import TOOL_LABELS, execute_read_tool
from services.ai_evaluation import _operations_tool_data
from services.operations_agent_graph import run_operations_agent, run_operations_agent_with_fallback, select_tools
from services.operations_agent_provider import GeminiOperationsAgentProvider


ROOT = Path(__file__).resolve().parents[1]


class ReadCursor:
    """Execute production SELECTs in SQLite with only MySQL clock syntax adapted."""
    def __init__(self, db):
        self.db = db
        self.closed = False

    def execute(self, sql):
        assert sql.strip().startswith('SELECT')
        sql = sql.replace('UTC_TIMESTAMP() - INTERVAL 3 DAY', "datetime('2026-09-21 12:00:00', '-3 days')")
        sql = sql.replace('TIMESTAMPDIFF(DAY, q.updated_at, UTC_TIMESTAMP())',
                          "CAST(julianday('2026-09-21 12:00:00') - julianday(q.updated_at) AS INTEGER)")
        sql = sql.replace('UTC_TIMESTAMP()', "'2026-09-21 12:00:00'")
        self.result = self.db.execute(sql)

    def fetchall(self):
        return [dict(row) for row in self.result.fetchall()]

    def close(self):
        self.closed = True


class OperationsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE roles(id INTEGER, code TEXT);
            CREATE TABLE staff_users(id INTEGER, role_id INTEGER, name TEXT, is_active INTEGER, email TEXT);
            CREATE TABLE members(id INTEGER, owner_id INTEGER, name TEXT, status TEXT, deleted_at TEXT, email TEXT);
            CREATE TABLE travel_requests(id INTEGER, member_id INTEGER, advisor_id INTEGER, status TEXT, destination TEXT);
            CREATE TABLE tasks(id INTEGER, assignee_id INTEGER, status TEXT, priority TEXT);
            CREATE TABLE trips(id INTEGER, request_id INTEGER);
            CREATE TABLE quotes(id INTEGER, trip_id INTEGER, quote_number TEXT, status TEXT, currency TEXT,
                total NUMERIC, updated_at TEXT, expires_at TEXT, version INTEGER, notes TEXT);
            CREATE TABLE orders(id INTEGER, quote_id INTEGER);
            INSERT INTO roles VALUES (1, 'advisor'), (2, 'admin');
            INSERT INTO staff_users VALUES (1,1,'A',1,'private@example.com'), (2,1,'B',1,NULL),
                (3,1,'Disabled',0,NULL), (4,2,'Admin',1,NULL), (5,1,'Empty',1,NULL);
            INSERT INTO members VALUES (1,1,'Traveler','active',NULL,'private@example.com'),
                (2,1,'Deleted','active','2026-01-01',NULL), (3,1,'Inactive','inactive',NULL,NULL);
            INSERT INTO travel_requests VALUES (1,1,1,'new','Tokyo'), (2,1,1,'completed','Kyoto'),
                (3,1,1,'cancelled','Osaka');
            INSERT INTO tasks VALUES (1,1,'open','high'), (2,1,'in_progress','urgent'),
                (3,1,'completed','high'), (4,2,'open','normal');
        ''')

    def run_tool(self, tool):
        cursor = ReadCursor(self.db)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        result = execute_read_tool(connection, tool)
        self.assertTrue(cursor.closed)
        connection.commit.assert_not_called()
        return result['items']

    def test_workload_counts_filters_order_and_privacy(self):
        rows = self.run_tool('advisor_workload')
        self.assertEqual([1,2,5], [r['advisor_id'] for r in rows])
        self.assertEqual(dict(advisor_id=1, advisor_name='A', active_members=1,
                              active_requests=1, open_tasks=2, high_priority_tasks=2), rows[0])
        self.assertEqual(0, rows[2]['open_tasks'])
        self.assertNotIn('private@example.com', str(rows))

    def add_quote(self, i, **overrides):
        data = dict(status='approved', updated_at='2026-09-18 12:00:00',
                    expires_at=None, version=1, trip_id=i)
        data.update(overrides)
        self.db.execute('INSERT INTO trips VALUES (?,1)', (i,))
        self.db.execute('INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)',
            (i,data['trip_id'],f'Q-{i}',data['status'],'TWD',100,data['updated_at'],
             data['expires_at'],data['version'],'PRIVATE NOTES'))

    def test_quote_boundary_status_versions_orders_expiry_and_privacy(self):
        self.add_quote(1)
        self.add_quote(2, status='pending_approval')
        self.add_quote(3, updated_at='2026-09-18 12:00:01')
        self.add_quote(4, status='draft')
        self.add_quote(5, status='rejected')
        self.add_quote(6, expires_at='2026-09-21 12:00:00')
        self.add_quote(7)
        self.db.execute('INSERT INTO orders VALUES (1,7)')
        self.add_quote(8)
        self.add_quote(9, trip_id=8, version=2, status='draft')
        rows = self.run_tool('quote_followups')
        self.assertEqual([1,2], [r['id'] for r in rows])
        self.assertEqual(3, rows[0]['stale_days'])
        self.assertEqual({'id','quote_number','status','currency','total','updated_at',
                          'expires_at','member_name','destination','stale_days'}, set(rows[0]))
        self.assertNotIn('PRIVATE', str(rows))
        self.assertNotIn('private@example.com', str(rows))
        self.db.execute("UPDATE members SET deleted_at='2026-01-01'")
        self.assertEqual([], self.run_tool('quote_followups'))
        self.db.execute('UPDATE members SET deleted_at=NULL')
        for status in ('completed','cancelled'):
            self.db.execute('UPDATE travel_requests SET status=?', (status,))
            self.assertEqual([], self.run_tool('quote_followups'))

    def test_limits_and_empty_results(self):
        self.assertEqual([], self.run_tool('quote_followups'))
        for i in range(1,13):
            self.add_quote(i)
            self.db.execute('INSERT INTO staff_users VALUES (?,1,?,1,NULL)', (10+i,str(i)))
        self.assertEqual(10, len(self.run_tool('quote_followups')))
        self.assertEqual(10, len(self.run_tool('advisor_workload')))

    def test_unknown_tool_and_query_failure_close_cursor(self):
        for tool in ('write_quote', 'quote_followups'):
            cursor = MagicMock()
            cursor.execute.side_effect = RuntimeError('database error')
            connection = MagicMock()
            connection.cursor.return_value = cursor
            with self.assertRaises((ValueError, RuntimeError)):
                execute_read_tool(connection, tool)
            cursor.close.assert_called_once()
            connection.commit.assert_not_called()


class OperationsV2FlowTests(unittest.TestCase):
    def test_multi_tool_routing_does_not_drop_new_tools(self):
        tools = select_tools('overview advisor workload quote task payment departure')
        self.assertEqual(set(TOOL_LABELS), set(tools))
        output = run_operations_agent('overview advisor workload quote task payment departure', _operations_tool_data)
        self.assertEqual(6, len(output['tools_used']))
        self.assertIn('Regression Advisor', output['answer'])
        self.assertIn('Q-REGRESSION', output['answer'])

    def test_new_tools_never_create_action_candidates(self):
        output = run_operations_agent('顧問報價建立任務並寄送', _operations_tool_data)
        self.assertEqual([], output['action_candidates'])
        self.assertTrue(output['guardrails']['requires_human_confirmation'])
        self.assertFalse(output['guardrails']['external_actions_executed'])

    def test_empty_and_fallback(self):
        provider = MagicMock()
        provider.run.side_effect = RuntimeError('offline')
        output = run_operations_agent_with_fallback('advisor quote', lambda _: {'items': []}, 'gemini', provider)
        self.assertTrue(output['fallback_used'])
        self.assertEqual(2, output['answer'].count('目前沒有符合條件'))

    def test_gemini_registers_and_invokes_only_read_tools(self):
        with patch('google.genai.Client') as client:
            chat = client.return_value.__enter__.return_value.chats.create
            def send(_):
                config = chat.call_args.kwargs['config']
                registered = {fn.__name__: fn for fn in config.tools}
                self.assertEqual(set(TOOL_LABELS), set(registered))
                self.assertGreaterEqual(
                    config.automatic_function_calling.maximum_remote_calls,
                    len(TOOL_LABELS),
                )
                registered['advisor_workload']()
                registered['quote_followups']()
                return SimpleNamespace(text='請由人員確認顧問工作量與停滯報價。')
            chat.return_value.send_message.side_effect = send
            execute = MagicMock(side_effect=_operations_tool_data)
            result = GeminiOperationsAgentProvider('test-key', 'test-model').run('顧問與報價', execute)
        self.assertEqual(['advisor_workload','quote_followups'], [r['tool'] for r in result['tool_results']])
        self.assertEqual(2, execute.call_count)

    def test_admin_console_exposes_v2_example_questions(self):
        html = (ROOT / 'admin' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('哪一位顧問目前手上的高優先案件最多？', html)
        self.assertIn('哪些旅客已經有報價，但三天沒有進展？', html)
        self.assertIn('最多六個唯讀工具', html)
