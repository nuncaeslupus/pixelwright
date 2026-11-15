"""`pw mcp`: MCP server over stdio whose tools are the CLI registry, one to one."""

from pixelwright.mcp.server import handle, serve, tool_schema, tools

__all__ = ["handle", "serve", "tool_schema", "tools"]
