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

    try:
        await user_model.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        print("index note:", exc)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        e1 = "alice" + "@" + "example.com"
        e2 = "bob" + "@" + "example.com"
        e3 = "carol" + "@" + "example.com"
        nid_a = "1234567890123"
        nid_b = "9876543210987"
        phone_a = "01712345678"
        phone_b = "+8801812345678"

        # 1. Register — full payload (citizen + nid + phone).
        r = await client.post(
            "/auth/register",
            json={
                "full_name": "Alice Hossain",
                "email": e1,
                "password": "goodpass1",
                "nid": nid_a,
                "phone": phone_a,
            },
        )
        print("REGISTER_FULL", r.status_code, r.json())
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]
        user_id = r.json()["user"]["id"]
        assert r.json()["user"]["role"] == "citizen"
        assert r.json()["user"]["nid"] == nid_a
        assert r.json()["user"]["phone"] == phone_a

        # 2. Duplicate email -> 409.
        r2 = await client.post(
            "/auth/register",
            json={"full_name": "Alice2", "email": e1, "password": "goodpass2"},
        )
        print("REGISTER_DUP_EMAIL", r2.status_code, r2.json())
        assert r2.status_code == 409

        # 3. Duplicate NID -> 409.
        r3 = await client.post(
            "/auth/register",
            json={"full_name": "Bob", "email": e2, "password": "goodpass3", "nid": nid_a},
        )
        print("REGISTER_DUP_NID", r3.status_code, r3.json())
        assert r3.status_code == 409

        # 4. Duplicate phone -> 409.
        r4 = await client.post(
            "/auth/register",
            json={"full_name": "Carol", "email": e3, "password": "goodpass4", "phone": phone_a},
        )
        print("REGISTER_DUP_PHONE", r4.status_code, r4.json())
        assert r4.status_code == 409

        # 5. Role escalation attempt -> ignored, role stays "citizen".
        r5 = await client.post(
            "/auth/register",
            json={
                "full_name": "Mallory",
                "email": "mallory" + "@" + "evil.com",
                "password": "goodpass5",
                "role": "admin",
            },
        )
        # Pydantic strips unknown fields by default; we never wrote `role` into
        # the model, so the payload is accepted but role must remain citizen.
        print("REGISTER_ROLE_TRY", r5.status_code, r5.json().get("user", {}).get("role"))
        assert r5.status_code == 201
        assert r5.json()["user"]["role"] == "citizen"

        # 6. Register with NO optional fields — must succeed (fields truly optional).
        r6 = await client.post(
            "/auth/register",
            json={
                "full_name": "Dave",
                "email": "dave" + "@" + "example.com",
                "password": "goodpass6",
            },
        )
        print("REGISTER_NO_OPTIONAL", r6.status_code, r6.json())
        assert r6.status_code == 201
        assert r6.json()["user"]["nid"] is None
        assert r6.json()["user"]["phone"] is None

        # 7. Invalid NID format -> 422.
        r7 = await client.post(
            "/auth/register",
            json={
                "full_name": "Eve",
                "email": "eve" + "@" + "example.com",
                "password": "goodpass7",
                "nid": "12345",
            },
        )
        print("REGISTER_BAD_NID", r7.status_code)
        assert r7.status_code == 422

        # 8. Invalid phone format -> 422.
        r8 = await client.post(
            "/auth/register",
            json={
                "full_name": "Frank",
                "email": "frank" + "@" + "example.com",
                "password": "goodpass8",
                "phone": "12345",
            },
        )
        print("REGISTER_BAD_PHONE", r8.status_code)
        assert r8.status_code == 422

        # 9. Login by email.
        r9 = await client.post(
            "/auth/login",
            json={"identifier": e1, "password": "goodpass1"},
        )
        print("LOGIN_EMAIL", r9.status_code, r9.json()["user"]["role"])
        assert r9.status_code == 200
        assert r9.json()["user"]["id"] == user_id

        # 10. Login by phone.
        r10 = await client.post(
            "/auth/login",
            json={"identifier": phone_a, "password": "goodpass1"},
        )
        print("LOGIN_PHONE", r10.status_code, r10.json()["user"]["id"])
        assert r10.status_code == 200
        assert r10.json()["user"]["id"] == user_id

        # 11. Login by NID.
        r11 = await client.post(
            "/auth/login",
            json={"identifier": nid_a, "password": "goodpass1"},
        )
        print("LOGIN_NID", r11.status_code, r11.json()["user"]["id"])
        assert r11.status_code == 200
        assert r11.json()["user"]["id"] == user_id

        # 12. Wrong password -> 401.
        r12 = await client.post(
            "/auth/login",
            json={"identifier": e1, "password": "wrongpass1"},
        )
        print("LOGIN_BAD", r12.status_code)
        assert r12.status_code == 401

        # 13. Unknown identifier -> 401 (no enumeration).
        r13 = await client.post(
            "/auth/login",
            json={"identifier": "nobody" + "@" + "nowhere.com", "password": "x"},
        )
        print("LOGIN_NO_USER", r13.status_code)
        assert r13.status_code == 401

        # 14. /me with valid token — full fields present.
        r14 = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        print("ME", r14.status_code, r14.json())
        assert r14.status_code == 200
        assert r14.json()["id"] == user_id
        assert r14.json()["nid"] == nid_a
        assert r14.json()["phone"] == phone_a

        # 15. /me without token -> 401.
        r15 = await client.get("/auth/me")
        print("ME_NO_TOKEN", r15.status_code)
        assert r15.status_code == 401

        # 16. /me with garbage token -> 401.
        r16 = await client.get("/auth/me", headers={"Authorization": "Bearer junk"})
        print("ME_BAD_TOKEN", r16.status_code)
        assert r16.status_code == 401

        # 17. Validation: short password + bad email -> 422.
        r17 = await client.post(
            "/auth/register",
            json={"full_name": "X", "email": "not-an-email", "password": "x"},
        )
        print("REGISTER_VALIDATION", r17.status_code, json.dumps(r17.json())[:200])
        assert r17.status_code == 422

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())