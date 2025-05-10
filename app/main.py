from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routers.user_router import router as user_router
from app.api.routers.wifi_router import router as wifi_router
from app.api.routers.handshake_router import router as handshake_router
from app.api.routers.dictionary_router import router as dictionary_router
from app.api.routers.wifi_crack_router import router as wifi_crack_router
from app.api.routers.wifi_deauth_router import router as wifi_deauth_router
from app.api.routers.wifi_evil_twin_router import router as wifi_evil_twin_router
from app.api.routers.wifi_cleanup_router import router as wifi_cleanup_router

app = FastAPI(debug=settings.DEBUG, title="WiFi Security Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router, prefix=settings.API_PREFIX)
app.include_router(wifi_router, prefix=settings.API_PREFIX)
app.include_router(handshake_router, prefix=settings.API_PREFIX)
app.include_router(dictionary_router, prefix=settings.API_PREFIX)
app.include_router(wifi_crack_router, prefix=settings.API_PREFIX)
app.include_router(wifi_deauth_router, prefix=settings.API_PREFIX)
app.include_router(wifi_evil_twin_router, prefix=settings.API_PREFIX)
app.include_router(wifi_cleanup_router, prefix=settings.API_PREFIX)
