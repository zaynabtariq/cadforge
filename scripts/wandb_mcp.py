"""Authenticated W&B MCP inspection without writing credentials to disk."""
import argparse,asyncio,json,httpx2
from cadforge.cloud import credential
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

async def main(tool,args):
 async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+credential()},timeout=60) as http:
  async with streamable_http_client('https://mcp.withwandb.com/mcp',http_client=http) as streams:
   async with ClientSession(streams[0],streams[1]) as session:
    await session.initialize()
    if tool=='schema':
     result=await session.list_tools()
     print(json.dumps([{'name':t.name,'inputSchema':t.input_schema} for t in result.tools if t.name in args.get('names',[])],indent=2))
    else:
     result=await session.call_tool(tool,arguments=args)
     print(result.model_dump_json(indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('tool');p.add_argument('--args',default='{}');a=p.parse_args()
 asyncio.run(main(a.tool,json.loads(a.args)))
