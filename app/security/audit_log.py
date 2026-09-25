import traceback
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger("audit")


def audit(
    event: str,
    user_id: str | None = None,
    admin_id: str | None = None,
    resource: str | None = None,
    details: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> None:
    log = logger.bind(
        event=event,
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id=user_id,
        admin_id=admin_id,
        resource=resource,
        **(details or {}),
    )
    if error:
        log.error(
            event,
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
        )
    else:
        log.info(event)
