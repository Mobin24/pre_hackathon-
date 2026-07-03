"""End-to-end auth smoke test using mongomock-motor + httpx ASGI transport."""
import asyncio
import json

import httpx
from mongomock_motor import AsyncMongoMockClient

import app.core.db as db_mod
import app.models.user as user_model
from app.main import app


async def main() -> None:
    # Patch the database module to use an in-memory mongomock client.
    mock_client = AsyncMongoMockClient()
    db_mod._client = mock_client
    db_mod._db = mock_client["drrcs_test"]

    # Ensure indexes on the mock (no-op for unique indexes in mongomock,
    # but keeps code path honest).
    try:
        await user_model.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        print("index note:", exc)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        email1 = "alice" + "@" + "example.com"
        email2 = "alice2" + "@" + "example.com"

        # 1. Register
        r = await client.post(
            "/auth/register",
            json={"name": "Alice", "email": email1, "password": "goodpass1"},
        )
        print("REGISTER", r.status_code, r.json())
        assert r.status_code == 201
        token = r.json()["access_token"]
        user_id = r.json()["user"]["id"]

        # 2. Duplicate registration -> 409
        r2 = await client.post(
            "/auth/register",
            json={"name": "Alice2", "email": email1, "password": "goodpass2"},
        )
        print("REGISTER_DUP", r2.status_code, r2.json())
        assert r2.status_code == 409

        # 3. Login
        r3 = await client.post(
            "/auth/login",
            json={"email": email1, "password": "goodpass1"},
        )
        print("LOGIN", r3.status_code, r3.json()["user"])
        assert r3.status_code == 200
        assert r3.json()["user"]["id"] == user_id

        # 4. Wrong password -> 401
        r4 = await client.post(
            "/auth/login",
            json={"email": email1, "password": "wrongpass1"},
        )
        print("LOGIN_BAD", r4.status_code, r4.json())
        assert r4.status_code == 401

        # 5. /me with valid token
        r5 = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        print("ME", r5.status_code, r5.json())
        assert r5.status_code == 200
        assert r5.json()["id"] == user_id

        # 6. /me without token -> 401
        r6 = await client.get("/auth/me")
        print("ME_NO_TOKEN", r6.status_code, r6.json())
        assert r6.status_code == 401

        # 7. /me with garbage token -> 401
        r7 = await client.get("/auth/me", headers={"Authorization": "Bearer junk"})
        print("ME_BAD_TOKEN", r7.status_code, r7.json())
        assert r7.status_code == 401

        # 8. Register validation: short password + bad email
        r8 = await client.post(
            "/auth/register",
            json={"name": "X", "email": "not-an-email", "password": "x"},
        )
        print("REGISTER_VALIDATION", r8.status_code, json.dumps(r8.json())[:200])
        assert r8.status_code == 422

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())