import argparse
import os
import requests
import cv2
import base64
import json
import time

DEFAULT_ENDPOINT = os.environ.get("DISPATCHER_ENDPOINT", "http://127.0.0.1:30000/infer")

parser = argparse.ArgumentParser(description="Send a single inference request to the dispatcher endpoint")
parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                    help="Dispatcher endpoint URL (default from DISPATCHER_ENDPOINT or localhost:30000)")
args = parser.parse_args()

im = cv2.imread("zidane.jpg")
im = cv2.resize(im, dsize=(256, 256), interpolation=cv2.INTER_CUBIC)
encoded = base64.b64encode(cv2.imencode(".jpeg", im)[1].tobytes()).decode("utf-8")

url = args.endpoint

t = time.perf_counter()
response = requests.post(url, data=json.dumps({"data": encoded}))
print(response.text, round(time.perf_counter() - t, 3))