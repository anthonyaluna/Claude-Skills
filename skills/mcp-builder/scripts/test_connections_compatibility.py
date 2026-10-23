import unittest
from types import SimpleNamespace

from connections import MCPConnection


class ConcreteConnection(MCPConnection):
    def _create_context(self):
        raise NotImplementedError


class MCPConnectionCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_tools_accepts_current_and_legacy_schema_fields(self):
        current_schema = {"type": "object", "properties": {"id": {"type": "string"}}}
        legacy_schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        tools = [
            SimpleNamespace(
                name="read_by_id",
                description="Read one record.",
                input_schema=current_schema,
            ),
            SimpleNamespace(
                name="read_by_name",
                description="Read one record by name.",
                inputSchema=legacy_schema,
            ),
        ]
        connection = ConcreteConnection()
        connection.session = SimpleNamespace(
            list_tools=lambda: _completed(SimpleNamespace(tools=tools))
        )

        listed = await connection.list_tools()

        self.assertEqual(
            listed,
            [
                {
                    "name": "read_by_id",
                    "description": "Read one record.",
                    "input_schema": current_schema,
                },
                {
                    "name": "read_by_name",
                    "description": "Read one record by name.",
                    "input_schema": legacy_schema,
                },
            ],
        )


async def _completed(value):
    return value


if __name__ == "__main__":
    unittest.main()
