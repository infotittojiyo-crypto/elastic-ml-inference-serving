# client.py — single-request sanity check against the dispatcher.
#
# Requires a test image named "zidane.jpg" in this folder. Any JPEG works —
# place your own image here (it is intentionally NOT included in the submission).
#
# Uses the stable port-forward endpoint (localhost:8000), set up with:
#   kubectl port-forward svc/dispatcher-service 8000:8000

import requests
import cv2
import base64
import json
import time

im = cv2.imread("zidane.jpg")
im = cv2.resize(im, dsize=(256, 256), interpolation=cv2.INTER_CUBIC)
encoded = base64.b64encode(cv2.imencode(".jpeg", im)[1].tobytes()).decode("utf-8")

t = time.perf_counter()
response = requests.post("http://localhost:8000/infer", data=json.dumps({"data": encoded}))
print(response.text, round(time.perf_counter() - t, 3))
