"""POST /api/schedule/lookup — find a learner's schedule card by full name."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from ...core.config import Settings
from ...models import LearnerRecord
from ...schemas.schedule import LookupRequest, LookupResponse, ScheduleCard
from ...services.sheets import name_tokens
from ...store import LearnerStore

MIN_TOKENS = 2  # first name + last name, so one word can't list everyone named "Али"
MIN_TOKEN_LEN = 2
MAX_RESULTS = 3  # more matches than this means the query is too vague to show anything

router = APIRouter(prefix="/api/schedule", tags=["schedule"])
log = logging.getLogger(__name__)


def client_ip(request: Request) -> str:
    """Rate-limit key. Behind N proxies, each appends the address it received the request from,
    so the Nth entry from the right of X-Forwarded-For is the real client. Entries further left
    are client-supplied and could be forged, so they are never used."""
    hops = request.app.state.settings.proxy_hops
    if hops:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    request.app.state.limiter.check(client_ip(request))


PENDING = "Уточняется"  # shown for room/email until the sheet has the column (or the cell is filled)


def to_card(r: LearnerRecord, expose_temp_password: bool) -> ScheduleCard:
    """Map an internal record to the public card. tumo_id and extra_info are never copied.

    room and default_email fall back to "Уточняется" when the sheet has no such column yet
    or the cell is empty; temp_password falls back to null.
    """
    return ScheduleCard(
        full_name=r.full_name,
        schedule=r.schedule or None,
        coach_name=r.coach_name or None,
        room=r.room or PENDING,
        default_email=r.default_email or PENDING,
        temp_password=(r.temp_password or None) if expose_temp_password else None,
        status_code=r.status_code,
        status=r.status or None,
    )


@router.post("/lookup", response_model=LookupResponse, dependencies=[Depends(rate_limit)])
def lookup(req: LookupRequest, request: Request) -> LookupResponse:
    """Always answers 200 with a status — sync problems never turn into a 5xx here."""
    try:
        return _lookup(req, request.app.state.store, request.app.state.settings)
    except Exception:
        log.exception("Lookup failed; answering 'unavailable'")
        return LookupResponse(status="unavailable")


def _lookup(req: LookupRequest, store: LearnerStore, settings: Settings) -> LookupResponse:
    snap = store.snapshot
    if snap is None:  # sheet unreachable and nothing cached yet (see /api/health for why)
        return LookupResponse(status="unavailable")
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
