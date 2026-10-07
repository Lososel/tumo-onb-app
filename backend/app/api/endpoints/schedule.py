"""POST /api/schedule/lookup — find a learner's schedule card by full name."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...core.config import Settings
from ...models import LearnerRecord
from ...schemas.schedule import LookupRequest, LookupResponse, ScheduleCard
from ...services.sheets import name_tokens
from ...store import LearnerStore

MIN_TOKENS = 2  # first name + last name, so one word can't list everyone named "Али"
MIN_TOKEN_LEN = 2
MAX_RESULTS = 3  # more matches than this means the query is too vague to show anything

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def rate_limit(request: Request) -> None:
    request.app.state.limiter.check(request.client.host if request.client else "unknown")


def to_card(r: LearnerRecord, expose_temp_password: bool) -> ScheduleCard:
    """Map an internal record to the public card. tumo_id and extra_info are never copied."""
    return ScheduleCard(
        full_name=r.full_name,
        schedule=r.schedule or None,
        coach_name=r.coach_name or None,
        room=r.room or None,
        default_email=r.default_email or None,
        temp_password=(r.temp_password or None) if expose_temp_password else None,
        status_code=r.status_code,
        status=r.status or None,
    )


@router.post("/lookup", response_model=LookupResponse, dependencies=[Depends(rate_limit)])
def lookup(req: LookupRequest, request: Request) -> LookupResponse:
    store: LearnerStore = request.app.state.store
    settings: Settings = request.app.state.settings

    snap = store.snapshot
    if snap is None:
        raise HTTPException(503, "Schedule data is temporarily unavailable. Please try again shortly.")
    updated = snap.fetched_at

    tokens = [t for t in name_tokens(req.query) if len(t) >= MIN_TOKEN_LEN]
    if len(tokens) < MIN_TOKENS:
        return LookupResponse(status="need_full_name", data_updated_at=updated)

    found = store.search(tokens)
    if not found:
        return LookupResponse(status="not_found", data_updated_at=updated)
    active = [r for r in found if r.active]
    if not active:
        return LookupResponse(status="inactive", data_updated_at=updated)
    if len(active) > MAX_RESULTS:
        return LookupResponse(status="too_many", data_updated_at=updated)
    return LookupResponse(
        status="ok",
        results=[to_card(r, settings.expose_temp_password) for r in active],
        data_updated_at=updated,
    )
