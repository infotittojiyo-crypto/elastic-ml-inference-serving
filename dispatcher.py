from aiohttp import web, ClientSession
import json

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