# dispatcher.py — stable NodePort entry point in front of the scaling pod set.
#
# Receives load from load_test.py and forwards each request to the internal
# ml-inference-service (ClusterIP), which load-balances across 1..5 pods.
#
# Design note: this is intentionally a SIMPLE pass-through. We tried queue-based
# variants (asyncio.Queue, backlog=2048, NUM_WORKERS tuning, longer ClientTimeout)
# in images v1..v6 to eliminate request drops. Instrumentation showed the queue
# absorbed bursts correctly (depth ~950) but drops persisted — they came from a
# genuine single-core compute ceiling, not the dispatcher. The simple version (v7)
# performed best and is the final one. Listens on port 8000.

from aiohttp import web, ClientSession

INFERENCE_SERVICE_URL = "http://ml-inference-service:8001/infer"


async def dispatch_handler(request):
    req = await request.read()
    async with ClientSession() as session:
        async with session.post(
            INFERENCE_SERVICE_URL,
            data=req,
            headers={"Content-Type": "application/json"}
        ) as resp:
            result = await resp.json()
            return web.json_response({"labels": result})


app = web.Application()
app.add_routes([web.post("/infer", dispatch_handler)])

if __name__ == '__main__':
    web.run_app(app, host="0.0.0.0", port=8000, access_log=None)
