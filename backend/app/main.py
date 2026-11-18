from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.demo import router as demo_router
from app.api.v1.router import router
from app.core.config import Settings
from app.core.database import Database


def create_app(settings: Settings | None = None, *, trends_preview: dict | None = None) -> FastAPI:
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
    if configuration.environment in ("development", "test"):
        application.include_router(demo_router, prefix=router.prefix)
    if configuration.environment == "development" and configuration.local_text_analysis == "1":
        from app.api.v1.local_text_analysis import router as local_text_analysis_router

        application.include_router(local_text_analysis_router, prefix=router.prefix)
    if configuration.environment == "development" and trends_preview is not None:
        from app.api.v1.trends_preview import router as trends_preview_router

        application.state.trends_preview = trends_preview
        application.include_router(trends_preview_router, prefix=router.prefix)
    if configuration.environment == "development" and configuration.local_research == "1":
        from app.api.v1.local_research import get_approved_request, router as local_research_router

        approvals = (("bluesky", configuration.bluesky_approved_request), ("lemmy", configuration.lemmy_approved_request),
                     ("wikimedia", configuration.wikimedia_approved_request),
                     ("civil_comments", configuration.civil_approved_request))
        configured = [(source, value) for source, value in approvals if value is not None]
        application.state.approved_research = get_approved_request(*configured[0]) if len(configured) == 1 else None
        application.include_router(local_research_router, prefix=router.prefix)
    return application


app = create_app()
