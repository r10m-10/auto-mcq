from fastapi import FastAPI

from app.db import init_db
from app.routers import credits as credits_router
from app.routers import device as device_router
from routers.offerwall import router as offerwall_router
from routers.device_delete import router as delete_router
from routers.config import router as config_router
from routers.admin import router as admin_router
from routers.ads import router as ads_router

app = FastAPI(title="Credit System API")

init_db()

app.include_router(device_router.router)
app.include_router(credits_router.router)
app.include_router(offerwall_router)
app.include_router(delete_router)
app.include_router(config_router)
app.include_router(admin_router)
app.include_router(ads_router)