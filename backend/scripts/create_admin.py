"""Безопасно создать первого production-администратора без demo seed."""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.infrastructure.database.models import User, UserRole
from app.infrastructure.database.session import AsyncSessionLocal, close_db


async def create_admin(email: str, full_name: str, password: str) -> None:
    if len(password) < 12:
        raise ValueError("Пароль должен содержать не менее 12 символов")

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            raise ValueError(f"Пользователь {email} уже существует")
        session.add(
            User(
                email=email,
                full_name=full_name,
                preferred_name=full_name.split()[0] if full_name else None,
                hashed_password=hash_password(password),
                role=UserRole.admin,
                is_active=True,
            )
        )
        await session.commit()


async def run(email: str, full_name: str, password: str) -> None:
    try:
        await create_admin(email, full_name, password)
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first production admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Новый пароль администратора: ")
    confirmation = getpass.getpass("Повторите пароль: ")
    if password != confirmation:
        raise SystemExit("Пароли не совпадают")

    asyncio.run(run(args.email.strip().lower(), args.name.strip(), password))
    print(f"Администратор {args.email} создан")


if __name__ == "__main__":
    main()
