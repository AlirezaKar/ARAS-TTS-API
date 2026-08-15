import logging

from fastapi import FastAPI

from app import __version__
from app.api.routes import router
from app.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Standalone Persian Text-to-Speech API with harakat fine-tuning and selectable TTS engines.",
)

app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_dirs()
    from app.services.pronunciation.db import init_schema

    init_schema(settings.pronunciation_db_path)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
