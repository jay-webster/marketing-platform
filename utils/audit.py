import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog


async def write_audit(
    db: AsyncSession,
    action: str,
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        target_id=target_id,
        event_metadata=metadata,
    )
    db.add(entry)
    # Caller is responsible for committing the transaction.
    # Never issue UPDATE or DELETE against audit_log.
