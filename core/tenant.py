"""Request-local tenant identity shared by hosted ARGUS services."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator


_current_user_id: ContextVar[str | None] = ContextVar(
    "argus_current_user_id",
    default=None,
)


def get_current_user_id() -> str | None:
    return _current_user_id.get()


@contextmanager
def tenant_scope(user_id: str) -> Iterator[None]:
    token = _current_user_id.set(str(user_id))
    try:
        yield
    finally:
        _current_user_id.reset(token)


# The hosted API serves many users from one process. There, a store that finds
# no user in scope must fail instead of falling back to the machine's shared
# files, which would mix users' data (and the operator's own key).
_hosted_mode = False


class MissingTenantError(RuntimeError):
    """A hosted request reached per-user storage without a user in scope."""


def enable_hosted_mode() -> None:
    global _hosted_mode
    _hosted_mode = True


def disable_hosted_mode() -> None:
    global _hosted_mode
    _hosted_mode = False


def hosted_mode_enabled() -> bool:
    return _hosted_mode


def require_local_storage(resource: str) -> None:
    """Call before using shared local files; raises in the hosted process."""
    if _hosted_mode:
        raise MissingTenantError(f"{resource} needs a signed-in user in the hosted app")
