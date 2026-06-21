from aiohttp import web, ClientSession, ClientTimeout
import asyncio

INFERENCE_SERVICE_URL = "http://ml-inference-service:8001/infer"

# Number of concurrent workers forwarding requests to ML pods.
# This roughly matches how many requests can be "in flight" to the
# backend at once - higher than 1 since K8s Service load-balances
# across multiple ml-inference pods.
NUM_WORKERS = 10

# Generous timeout - we'd rather wait than drop a request.
REQUEST_TIMEOUT = ClientTimeout(total=300)

request_queue = None  # created inside the running event loop on startup
session = None        # shared ClientSession, created on startup


async def worker(worker_id):
    """Pulls jobs from the queue forever and forwards them to the ML service."""
    while True:
        request_data, future = await request_queue.get()
        try:
            async with session.post(
                INFERENCE_SERVICE_URL,
                data=request_data,
                headers={"Content-Type": "application/json"},
            ) as resp:
                body = await resp.read()
                if not future.done():
                    future.set_result(body)
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
        finally:
            request_queue.task_done()


async def on_startup(app):
    global request_queue, session
    request_queue = asyncio.Queue()
    session = ClientSession(timeout=REQUEST_TIMEOUT)
    for i in range(NUM_WORKERS):
        asyncio.create_task(worker(i))
    print(f"Dispatcher started with {NUM_WORKERS} workers, backlog=2048", flush=True)


async def dispatch_handler(request):
    req_body = await request.read()
    queue_size = request_queue.qsize()
    if queue_size > 0 and queue_size % 50 == 0:
        print(f"Queue depth: {queue_size}", flush=True)
    future = asyncio.get_event_loop().create_future()
    await request_queue.put((req_body, future))
    try:
        result = await future
        return web.Response(body=result, content_type="application/json")
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=502)


async def on_cleanup(app):
    if session:
        await session.close()


app = web.Application()
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)
app.add_routes([web.post("/infer", dispatch_handler)])

if __name__ == '__main__':
    web.run_app(app, host="0.0.0.0", port=8000, access_log=None, backlog=2048)