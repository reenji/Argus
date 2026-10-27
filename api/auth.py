"""FastAPI authentication dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_access_token


bearer = HTTPBearer(auto_error=False)


def _user_for_token(token: str, db: Session) -> User:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user = db.get(User, str(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    if int(payload.get("ver", 0)) != user.session_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return _user_for_token(credentials.credentials, db)


# Browsers cannot set headers on a WebSocket, so the web client offers its
# token as a subprotocol; unlike a query string it stays out of access logs.
WEBSOCKET_PROTOCOL = "argus.v1"
WEBSOCKET_TOKEN_PREFIX = "bearer."


def websocket_user(websocket: WebSocket, db: Session) -> User:
    token = ""
    for protocol in websocket.scope.get("subprotocols", []):
        if protocol.startswith(WEBSOCKET_TOKEN_PREFIX):
            token = protocol.removeprefix(WEBSOCKET_TOKEN_PREFIX)
    if not token:
        authorization = websocket.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _user_for_token(token, db)
