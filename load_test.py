from barazmoon import BarAzmoon
import cv2
import base64
import json

# Encode image
im = cv2.imread("zidane.jpg")
im = cv2.resize(im, dsize=(256, 256), interpolation=cv2.INTER_CUBIC)
encoded = base64.b64encode(cv2.imencode(".jpeg", im)[1].tobytes()).decode("utf-8")
data = json.dumps({"data": encoded}).encode("utf-8")

# Workload: low → high → low (seconds)
workload = [2]*30 + [5]*30 + [10]*30 + [5]*30 + [2]*30

class MLLoadTester(BarAzmoon):
    def get_request_data(self):
        return "req-1", data

    def process_response(self, data_id, response):
        return True

tester = MLLoadTester(
    endpoint="http://127.0.0.1:39911/infer",
    workload=workload,
    http_method="post"
)

tester.start()