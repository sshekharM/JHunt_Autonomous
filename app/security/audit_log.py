import traceback
import structlog
from datetime import datetime, timezone
from typing import Optional, Any

logger = structlog.get_logger("audit")


def audit(
    event: str,
    user_id: Optional[str] = None,
    admin_id: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    error: Optional[Exception] = None,
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
