from fastapi import FastAPI

from app.db import init_db
from app.routers import credits as credits_router
from app.routers import device as device_router
from routers.offerwall import router as offerwall_router

app = FastAPI(title="Credit System API")

init_db()

app.include_router(device_router.router)
app.include_router(credits_router.router)
app.include_router(offerwall_router)
