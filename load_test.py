# load_test.py — replays the workload trace against the dispatcher using barazmoon.
#
# Requires a test image named "zidane.jpg" in this folder (any JPEG; not included).
#
# Uses the stable port-forward endpoint (localhost:8000), set up with:
#   kubectl port-forward svc/dispatcher-service 8000:8000

from barazmoon import BarAzmoon
import cv2
import base64
import json

# Encode image
im = cv2.imread("zidane.jpg")
im = cv2.resize(im, dsize=(256, 256), interpolation=cv2.INTER_CUBIC)
encoded = base64.b64encode(cv2.imencode(".jpeg", im)[1].tobytes()).decode("utf-8")
data = json.dumps({"data": encoded}).encode("utf-8")

# Workload is read from workload_scaled.txt (peak 36 req/s), NOT the original
# workload.txt (peak 44 req/s). The original peak exceeds our cluster's measured
# throughput ceiling (~36-38 req/s at 5 single-core pods), which caused unavoidable
# drops. Per the instructor's guidance ("scale down the request workload to match
# your resources"), we scaled the trace by 0.818, preserving its shape. See REPORT.md.
with open("workload_scaled.txt") as f:
    workload = [int(x) for x in f.read().split()]


class MLLoadTester(BarAzmoon):
    def get_request_data(self):
        return "req-1", data

    def process_response(self, data_id, response):
        return True


tester = MLLoadTester(
    endpoint="http://localhost:8000/infer",
    workload=workload,
    http_method="post"
)

tester.start()
