FROM python:3.11-slim

WORKDIR /app

COPY services/inference /app
RUN pip install --no-cache-dir .

# Bake COCO-pretrained weights into the image at BUILD time (needs internet
# in the build environment) so the running container never needs internet —
# the actual requirement for an air-gapped deployment.
RUN python -c "from torchvision.models.detection import fasterrcnn_resnet50_fpn; fasterrcnn_resnet50_fpn(weights='DEFAULT')"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
