from torchvision.models import resnet18, ResNet18_Weights
import torch
import base64
from PIL import Image
import io
import numpy as np
from aiohttp import web
import time
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST

preprocessor = ResNet18_Weights.IMAGENET1K_V1.transforms()

torch.set_num_interop_threads(1)
torch.set_num_threads(1)

resnet_model = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
resnet_model.eval()

# Prometheus metrics
REQUEST_LATENCY = Histogram('inference_latency_seconds', 
                            'Time spent processing inference request')
REQUEST_COUNT = Counter('inference_requests_total', 
                       'Total number of inference requests')

def infer(d):
    t = time.perf_counter()
    decoded = base64.b64decode(d["data"])
    inp = Image.open(io.BytesIO(decoded))
    inp = np.array(preprocessor(inp))
    inp = torch.from_numpy(np.array([inp]))
    
    preds = resnet_model(inp)
    labels = []
    for idx in list(preds[0].sort()[1])[-1:-6:-1]:
        labels.append(ResNet18_Weights.IMAGENET1K_V1.meta["categories"][idx])
    print("Server-side processing took:", round(time.perf_counter() - t, 3))
    return labels

app = web.Application()

async def infer_handler(request):
    REQUEST_COUNT.inc()
    with REQUEST_LATENCY.time():
        req = await request.json()
        result = infer(req)
    return web.json_response(result)

async def metrics_handler(request):
    return web.Response(body=generate_latest(), 
                       content_type="text/plain")

app.add_routes([
    web.post("/infer", infer_handler),
    web.get("/metrics", metrics_handler),
])

if __name__ == '__main__':
    web.run_app(app, host="0.0.0.0", port=8001, access_log=None)