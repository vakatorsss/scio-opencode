"""Local stdio MCP catalog for OpenCode. OpenCode owns permission approval."""
import argparse
import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from workspace_tools import WorkspaceTools


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True)
    args=parser.parse_args()
    catalog=WorkspaceTools(args.workspace,approve=lambda *_:True)
    server=Server('scio-workspace')
    @server.list_tools()
    async def list_tools():return [Tool(**t) for t in catalog.definitions()]
    @server.call_tool()
    async def call_tool(name,arguments):
        result=await asyncio.to_thread(catalog.call,name,arguments)
        return [TextContent(type='text',text=json.dumps(result,ensure_ascii=False,default=str))]
    async with stdio_server() as (read,write):
        await server.run(read,write,server.create_initialization_options())


if __name__=='__main__':asyncio.run(main())
