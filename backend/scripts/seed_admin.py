"""Create or rotate an admin account.

Admins can ONLY be provisioned through this script. The HTTP /auth/register
endpoint refuses to set role to "admin" — that contract is non-negotiable.

Usage (run from `backend/` with the virtualenv active):

    python -m scripts.seed_admin \\
        --email admin@reliefgrid.com \\
        --password "strongPass!1" \\
        --full-name "Ops Admin"

Idempotent: if the email already exists, the password and name are rotated
and the role is forced to "admin". NID/phone are NOT set on admin accounts
unless you pass them explicitly.
"""
import argparse
import asyncio
import getpass
import sys
from pathlib import Path

# Make `app.*` importable when invoked as `python -m scripts.seed_admin`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402
from app.core.security import hash_password  # noqa: E402


async def upsert_admin(email: str, password: str, full_name: str, nid: str | None, phone: str | None) -> None:
    db = get_database()
    existing = await db["users"].find_one({"email": email.lower()})
    pwd_hash = hash_password(password)

    if existing:
        await db["users"].update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "password_hash": pwd_hash,
                    "role": "admin",
                    "name": full_name or existing.get("name", "Admin"),
                    "nid": nid,
                    "phone": phone,
                }
            },
        )
        print(f"  ↻ updated existing user {email} → admin")
        return

    await db["users"].insert_one(
        {
            "name": full_name,
            "email": email.lower(),
            "password_hash": pwd_hash,
            "role": "admin",
            "nid": nid,
            "phone": phone,
        }
    )
    print(f"  ✓ created admin {email}")


def prompt_password_if_missing(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    pwd = getpass.getpass("Admin password (min 8 chars): ")
    if len(pwd) < 8:
        sys.exit("Password must be at least 8 characters.")
    pwd2 = getpass.getpass("Repeat password: ")
    if pwd != pwd2:
        sys.exit("Passwords do not match.")
    return pwd


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or rotate an admin account.")
    parser.add_argument("--email", required=True, help="Admin email (used as login identifier)")
    parser.add_argument("--password", help="Admin password (prompted if omitted)")
    parser.add_argument("--full-name", default="Admin", help="Display name")
    parser.add_argument("--nid", default=None, help="Optional BD national ID")
    parser.add_argument("--phone", default=None, help="Optional BD phone number")
    return parser.parse_args(argv)


async def main_async() -> None:
    args = parse_args()
    password = prompt_password_if_missing(args)
    try:
        await connect_to_mongo()
        await upsert_admin(args.email, password, args.full_name, args.nid, args.phone)
    finally:
        await close_mongo_connection()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()