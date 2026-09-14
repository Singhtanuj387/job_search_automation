"""
Session and Client Identifier Utility for Anonymous Device Isolation.
Extracts and sanitizes device session tokens from headers, query params, or cookies.
"""
import re
from typing import Optional
from fastapi import Header, Query, Request


def get_client_id(
    request: Request,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    query_session_id: Optional[str] = Query(None, alias="session_id"),
) -> str:
    """
    Extracts the anonymous client session ID for isolating profiles,
    application trackers, chat histories, and API settings per device.
    """
    raw_id = (
        x_session_id
        or query_session_id
        or request.query_params.get("session_id")
        or getattr(request.state, "client_id", None)
        or request.cookies.get("session_id")
        or "default"
    )
    clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(raw_id).strip())[:64]
    return clean_id if len(clean_id) >= 4 else "default"
