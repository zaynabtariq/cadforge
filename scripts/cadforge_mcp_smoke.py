"""Exercise actual CAD tools through an MCP subprocess transport."""
import asyncio,json,sys
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client

async def main():
 params=StdioServerParameters(command=sys.executable,args=['-m','cadforge.mcpserver','--weave'])
 async with stdio_client(params) as streams:
  async with ClientSession(streams[0],streams[1]) as session:
   await session.initialize()
   print('tools',[x.name for x in (await session.list_tools()).tools])
   result=await session.call_tool('measure_fastener_fit',arguments={'fastener_diameter':2.5,'radial_clearance':.15,'bore_diameter':2.5,'boss_outer_diameter':2.7})
   print('failed_fit',result.model_dump_json())
   good=await session.call_tool('apply_learned_fastener',arguments={'fastener_diameter':2.5,'radial_clearance':.15,'min_wall':1.5})
   print('learned_parameters',good.model_dump_json())
   changed=await session.call_tool('widen_robot_link',arguments={'parameters':{'width':20.,'center_distance':80.},'new_width':30.})
   print('robot_width_change',changed.model_dump_json())
   rejected=await session.call_tool('widen_robot_link',arguments={'parameters':{'width':20.,'center_distance':80.},'new_width':50.})
   print('robot_invalid_change',rejected.model_dump_json())
asyncio.run(main())
