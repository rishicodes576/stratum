"""Create an initial tenant/admin. No public self-registration or default production credentials."""

import argparse
import asyncio
import getpass
import os

from sqlalchemy import select

from app.db import Session, engine
from app.models import Tenant, User
from app.security import hash_password


async def bootstrap(email: str, name: str, workspace: str, password: str):
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Use a password between 12 and 128 characters")
    async with Session() as session, session.begin():
        if await session.scalar(select(User).where(User.email == email.lower())):
            raise ValueError("That email already exists")
        tenant = Tenant(name=workspace)
        session.add(tenant)
        await session.flush()
        session.add(
            User(
                tenant_id=tenant.id,
                name=name,
                email=email.lower(),
                role="admin",
                password_hash=hash_password(password),
            )
        )
    await engine.dispose()
    print("Workspace and administrator created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    password = os.getenv("BOOTSTRAP_PASSWORD") or getpass.getpass("Administrator password: ")
    asyncio.run(bootstrap(args.email, args.name, args.workspace, password))
