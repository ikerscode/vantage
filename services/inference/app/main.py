from fastapi import FastAPI

from app.routers import detect, health

app = FastAPI(title="VANTAGE Inference")
app.include_router(health.router)
app.include_router(detect.router)
