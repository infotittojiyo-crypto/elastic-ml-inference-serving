FROM python:3.11-slim

WORKDIR /app

# torch/torchvision from the CPU wheel index (CPU-only node, smaller image).
RUN pip install --no-cache-dir torch==2.3.0 torchvision==0.18.0 \
        --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir \
        aiohttp==3.9.5 \
        opencv-python-headless==4.10.0.84 \
        requests==2.32.3 \
        pillow==10.2.0 \
        numpy \
        prometheus-client==0.25.0

COPY model_server.py .

CMD ["python", "model_server.py"]
