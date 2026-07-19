"""FastAPI route aggregation.

Feature modules own their endpoints; this package keeps the public
`router` and `set_globals` API used by `src.main`.
"""

import sqlite3

from fastapi import APIRouter

from src.routes.admin import router as admin_router
from src.routes.chat import router as chat_router
from src.routes.dependencies import set_connection
from src.routes.digest import router as digest_router
from src.routes.extensions import router as extensions_router
from src.routes.imports import router as imports_router
from src.routes.knowledge import router as knowledge_router
from src.routes.notes import router as notes_router
from src.routes.traces import router as traces_router
from src.routes.user import router as user_router

router = APIRouter()

for feature_router in (
    chat_router,
    notes_router,
    traces_router,
    digest_router,
    knowledge_router,
    imports_router,
    user_router,
    extensions_router,
    admin_router,
):
    router.include_router(feature_router)


def set_globals(conn: sqlite3.Connection) -> None:
    """Initialize dependencies shared by all route modules."""
    set_connection(conn)
