from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router
from app.core.config import Settings
from app.core.database import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Creating an engine is lazy: startup does not require PostgreSQL to be online.
        database = Database(configuration) if configuration.database_is_configured else None
        application.state.database = database
        try:
            yield
        finally:
            if database is not None:
                database.close()
            application.state.database = None

    application = FastAPI(
        title=configuration.service_name, version="0.1.0", lifespan=lifespan
    )
    application.state.settings = configuration
    application.include_router(router)
    return application


app = create_app()
