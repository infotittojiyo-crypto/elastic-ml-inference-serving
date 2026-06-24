from barazmoon import BarAzmoon
import cv2
import base64
import json
import os
import argparse

DEFAULT_ENDPOINT = os.environ.get("DISPATCHER_ENDPOINT", "http://127.0.0.1:30000/infer")

parser = argparse.ArgumentParser(description="Run burst load test against dispatcher endpoint")
parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                    help="Dispatcher endpoint URL (default from DISPATCHER_ENDPOINT or localhost:30000)")
args = parser.parse_args()

# Encode image
im = cv2.imread("zidane.jpg")
im = cv2.resize(im, dsize=(256, 256), interpolation=cv2.INTER_CUBIC)
encoded = base64.b64encode(cv2.imencode(".jpeg", im)[1].tobytes()).decode("utf-8")
data = json.dumps({"data": encoded}).encode("utf-8")

#  workload, loaded from file
with open("workload.txt") as f:
    workload = [int(x) for x in f.read().split()]

class MLLoadTester(BarAzmoon):
    def get_request_data(self):
        return "req-1", data

    def process_response(self, data_id, response):
        return True

tester = MLLoadTester(
    endpoint=args.endpoint,
    workload=workload,
    http_method="post"
)

tester.start()