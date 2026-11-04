from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.bootstrap import apply_schema, seed_if_empty
from app.db import get_pool, init_pool
from app.services import (
    RequestError,
    bulk_issue,
    fetch_actor,
    get_certificate,
    list_actors,
    list_certificates,
    list_courses,
    revoke_certificate,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_pool()
    with get_pool().connection() as conn:
        with conn.transaction():
            apply_schema(conn)
            seed_if_empty(conn)
    yield


app = FastAPI(title="Certificate Admin Console", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BulkIssueBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    course_id: str


@app.exception_handler(RequestError)
def handle_request_error(_request, exc: RequestError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


def get_actor(x_actor_token: Annotated[str | None, Header()] = None) -> dict:
    if not x_actor_token:
        raise RequestError(401, "Missing actor token")
    actor = fetch_actor(x_actor_token)
    if actor is None:
        raise RequestError(401, "Unknown actor token")
    return actor


@app.get("/api/health")
def health():
    with get_pool().connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


@app.get("/api/actors")
def actors():
    return {"actors": list_actors()}


@app.get("/api/me")
def me(actor: dict = Depends(get_actor)):
    return {
        "email": actor["email"],
        "tenant_id": actor["tenant_id"],
        "tenant_name": actor["tenant_name"],
        "timezone": actor["timezone"],
    }


@app.get("/api/courses")
def courses(actor: dict = Depends(get_actor)):
    return {"courses": list_courses(actor)}


@app.get("/api/certificates")
def certificates(
    actor: dict = Depends(get_actor),
    q: str = Query(""),
    sort: str = Query("issued_date"),
    order: str = Query("desc"),
    page: int = Query(1),
    page_size: int = Query(20),
):
    return list_certificates(
        actor,
        q=q.strip(),
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@app.get("/api/certificates/{certificate_id}")
def certificate_detail(certificate_id: str, actor: dict = Depends(get_actor)):
    return get_certificate(actor, certificate_id)


@app.post("/api/certificates/bulk-issue")
def issue_certificates(
    body: BulkIssueBody,
    actor: dict = Depends(get_actor),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if idempotency_key is None or not idempotency_key.strip():
        raise RequestError(400, "Idempotency-Key is required")
    if len(idempotency_key) > 255:
        raise RequestError(400, "Idempotency-Key is too long")
    if not body.course_id.strip():
        raise RequestError(400, "course_id is required")
    status, payload = bulk_issue(actor, idempotency_key, body.model_dump())
    return JSONResponse(status_code=status, content=payload)


@app.post("/api/certificates/{certificate_id}/revoke")
def revoke(certificate_id: str, actor: dict = Depends(get_actor)):
    return revoke_certificate(actor, certificate_id)
