"""Client CRUD endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.infrastructure.database.models import AuditLog, Client, ClientRepresentative, User
from app.infrastructure.database.session import get_session
from app.schemas.clients import (
    ClientCreate,
    ClientRepresentativeCreate,
    ClientRepresentativeResponse,
    ClientResponse,
    ClientUpdate,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/clients", tags=["clients"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_client_or_404(client_id: int, session: AsyncSession) -> Client:
    result = await session.execute(
        select(Client)
        .options(selectinload(Client.representatives))
        .where(Client.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


# ---------------------------------------------------------------------------
# List / create
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[ClientResponse])
async def list_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> PaginatedResponse[ClientResponse]:
    """List all clients (paginated)."""
    total_result = await session.execute(select(func.count(Client.id)))
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        select(Client)
        .options(selectinload(Client.representatives))
        .offset(offset)
        .limit(page_size)
        .order_by(Client.id)
    )
    clients = result.scalars().all()
    items = [ClientResponse.model_validate(c) for c in clients]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClientResponse:
    """Create a new client, optionally with representatives."""
    reps_data = payload.representatives or []
    client_data = payload.model_dump(exclude={"representatives"})
    client = Client(**client_data, created_by_user_id=current_user.id)
    session.add(client)
    await session.flush()

    for rep_data in reps_data:
        rep = ClientRepresentative(**rep_data.model_dump(), client_id=client.id)
        session.add(rep)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="client_create",
        entity_type="Client",
        entity_id=str(client.id),
        new_value_json={"full_name_or_company_name": client.full_name_or_company_name},
    )
    session.add(audit)

    await session.flush()
    result = await session.execute(
        select(Client).options(selectinload(Client.representatives)).where(Client.id == client.id)
    )
    client = result.scalar_one()
    return ClientResponse.model_validate(client)


# ---------------------------------------------------------------------------
# Get / update
# ---------------------------------------------------------------------------


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> ClientResponse:
    """Get a single client by ID."""
    client = await _get_client_or_404(client_id, session)
    return ClientResponse.model_validate(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClientResponse:
    """Update a client's details."""
    client = await _get_client_or_404(client_id, session)

    old_val = {"full_name_or_company_name": client.full_name_or_company_name}
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(client, field, value)

    audit = AuditLog(
        user_id=current_user.id,
        action="client_update",
        entity_type="Client",
        entity_id=str(client_id),
        old_value_json=old_val,
        new_value_json={"full_name_or_company_name": client.full_name_or_company_name},
    )
    session.add(audit)

    await session.flush()
    await session.refresh(client)
    return ClientResponse.model_validate(client)


# ---------------------------------------------------------------------------
# Representatives
# ---------------------------------------------------------------------------


@router.get("/{client_id}/representatives", response_model=List[ClientRepresentativeResponse])
async def list_representatives(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> List[ClientRepresentativeResponse]:
    """List all representatives for a client."""
    await _get_client_or_404(client_id, session)  # validates existence
    result = await session.execute(
        select(ClientRepresentative).where(ClientRepresentative.client_id == client_id)
    )
    reps = result.scalars().all()
    return [ClientRepresentativeResponse.model_validate(r) for r in reps]


@router.post(
    "/{client_id}/representatives",
    response_model=ClientRepresentativeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_representative(
    client_id: int,
    payload: ClientRepresentativeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ClientRepresentativeResponse:
    """Add a representative to an existing client."""
    client_result = await session.execute(select(Client).where(Client.id == client_id))
    if not client_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    rep = ClientRepresentative(**payload.model_dump(), client_id=client_id)
    session.add(rep)

    audit = AuditLog(
        user_id=current_user.id,
        action="representative_add",
        entity_type="ClientRepresentative",
        entity_id=str(client_id),
        new_value_json={"full_name": payload.full_name},
    )
    session.add(audit)

    await session.flush()
    await session.refresh(rep)
    return ClientRepresentativeResponse.model_validate(rep)
