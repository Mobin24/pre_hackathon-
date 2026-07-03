"""End-to-end AI pipeline smoke test (no real OpenAI calls).

We monkeypatch `app.core.openai_client.chat_json` so the pipeline runs
against canned responses. This exercises:
- Submit  →  scheduled background task picks up the doc
- run_text_ai + run_image_ai + combine  →  AIOutput persisted
- status transitions: pending_ai  →  processed
- no-image path uses deterministic fallback (no combine API call)
- AI failure path   → status='failed', error recorded
- admin reprocess endpoint
- recover_pending re-queues stale pending_ai docs on startup
"""
import asyncio
import io
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# Must be set BEFORE the app loads so is_configured() is True.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")
# Speed up recovery threshold so the test doesn't have to wait.
os.environ.setdefault("AI_RECOVERY_THRESHOLD_SECONDS", "1")

import httpx
from mongomock_motor import AsyncMongoMockClient

import app.core.db as db_mod
import app.models.user as user_model
from app.main import app

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x9c\xb1\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)

# --- canned responses used by the mock ---------------------------------------
TEXT_OK: Dict[str, Any] = {
    "type": "flood",
    "severity": "high",
    "urgency_score": 78,
    "assistance_detected": ["rescue_team", "water"],
    "summary": "Severe flooding reported in Baipail industrial zone.",
    "confidence": 0.9,
    "language": "en",
    "raw_signal": {"keywords": ["flood", "water"], "tone": "urgent"},
}
IMAGE_OK: Dict[str, Any] = {
    "has_image": True,
    "caption": "Brown floodwater covering an industrial access road.",
    "type_hint": "flood",
    "severity_hint": "critical",
    "urgency_hint": 92,
    "safety_flag": "flood_water",
    "confidence": 0.85,
}
COMBINE_OK: Dict[str, Any] = {
    "type": "flood",
    "severity": "critical",
    "urgency_score": 88,
    "summary": "Flash flood with submerged roads near Baipail. Image confirms water inundating the area.",
    "recommendation": "Dispatch a rescue team and rescue boat within the hour.",
    "assistance_needed": ["rescue_team", "rescue_boat", "water"],
    "confidence": 0.9,
}


def make_chat_json(
    *,
    fail_text: bool = False,
    fail_image: bool = False,
    fail_combine: bool = False,
):
    """Return a fake `chat_json` that dispatches by stage."""

    async def fake_chat_json(*, model: str, messages, **kwargs):
        sys_content = ""
        if messages and isinstance(messages[0], dict):
            sys_content = messages[0].get("content") or ""
        print(f"[FAKE_CHAT_JSON] model={model} sys_head={sys_content[:40]!r}")
        if "triage analyst" in sys_content:  # text stage
            print(f"[FAKE_CHAT_JSON] text stage, fail_text={fail_text}")
            if fail_text:
                raise RuntimeError("simulated text failure")
            return TEXT_OK
        if "disaster-scene photos" in sys_content:  # vision stage
            if fail_image:
                raise RuntimeError("simulated vision failure")
            return IMAGE_OK
        if "senior dispatcher" in sys_content:  # combine stage
            if fail_combine:
                raise RuntimeError("simulated combine failure")
            return COMBINE_OK
        return TEXT_OK

    return fake_chat_json


# --- helpers -----------------------------------------------------------------
async def register_citizen(client: httpx.AsyncClient, email: str, name: str) -> str:
    r = await client.post(
        "/auth/register",
        json={"full_name": name, "email": email, "password": "goodpass1"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


async def seed_admin(email: str) -> str:
    from app.core.security import hash_password
    admin_doc = {
        "name": "Admin User",
        "email": email,
        "password_hash": hash_password("adminpass1"),
        "role": "admin",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db_mod._db[user_model.COLLECTION].insert_one(admin_doc)
    return email


async def login(client: httpx.AsyncClient, identifier: str, password: str) -> str:
    r = await client.post(
        "/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def wait_for_status(
    client: httpx.AsyncClient,
    token: str,
    report_id: str,
    target: str,
    timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """Poll GET /api/report/{id} until status == target or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    last: Dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(
            f"/api/report/{report_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        last = r.json()
        if last.get("status") == target:
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for status={target}, got {last.get('status')}")


def submit_form(token: str, description: str, *, with_image: bool) -> Dict[str, Any]:
    location_obj = {
        "division": "Dhaka",
        "district": "Gazipur",
        "upazila": "Kaliakair",
        "area": "Baipail industrial zone",
        "coords": {"lat": 24.0693, "lng": 90.2221},
    }
    data = {
        "description": description,
        "location": str(location_obj).replace("'", '"'),
        "affected_count": "12",
        "assistance": '["rescue_team", "water"]',
        "immediate_danger": "true",
        "incident_time": "within_1h",
    }
    files = [
        ("images", ("flood.png", io.BytesIO(TINY_PNG), "image/png")),
    ] if with_image else []
    return {"data": data, "files": files, "headers": {"Authorization": f"Bearer {token}"}}


# --- main --------------------------------------------------------------------
async def main() -> None:
    mock_client = AsyncMongoMockClient()
    db_mod._client = mock_client
    db_mod._db = mock_client["drrcs_test"]

    try:
        await user_model.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        print("index note:", exc)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        # ---------- happy path: text + image + combine → processed -------------
        token = await register_citizen(client, "ai_alice@" + "example.com", "AI Alice")

        fake = make_chat_json()
        import app.ml.ai_pipeline as _pl
        _real_chat_json = _pl.chat_json
        _pl.chat_json = fake
        try:
            sf = submit_form(
                token,
                "Severe flooding in Baipail, water rising fast, need rescue.",
                with_image=True,
            )
            r = await client.post(
                "/api/report/submit",
                data=sf["data"],
                files=sf["files"],
                headers=sf["headers"],
            )
            print("SUBMIT", r.status_code, {k: r.json().get(k) for k in ("id", "status")})
            assert r.status_code == 201, r.text
            assert r.json()["status"] == "pending_ai"
            report_id = r.json()["id"]

            # Patch stays active while the background task completes.
            final = await wait_for_status(client, token, report_id, "processed", timeout_s=5.0)
            print("FINAL_STATUS", final["status"])
            assert final["status"] == "processed"
            assert final["ai_output"] is not None
            ao = final["ai_output"]
            print("AI_KEYS", sorted(ao.keys()))
            assert "combined" in ao
            assert "text" in ao
            assert "image" in ao
            assert "models" in ao
            assert ao["combined"]["type"] == "flood"
            assert ao["combined"]["severity"] == "critical"
            assert ao["combined"]["urgency_score"] == 88
            assert "rescue_team" in ao["combined"]["assistance_needed"]
            assert ao["combined"]["recommendation"].strip() != ""
            assert ao["text"]["type"] == "flood"
            assert ao["text"]["urgency_score"] == 78
            assert ao["image"]["has_image"] is True
            assert ao["image"]["severity_hint"] == "critical"
            assert isinstance(ao["models"].get("text"), str)
        finally:
            _pl.chat_json = _real_chat_json

        # ---------- no-image path: combine API is NOT called ------------------
        fake2 = make_chat_json()
        _real_chat_json_2 = _pl.chat_json
        _pl.chat_json = fake2
        try:
            sf2 = submit_form(
                token,
                "Water rising on the main road, no images attached right now.",
                with_image=False,
            )
            r = await client.post(
                "/api/report/submit",
                data=sf2["data"],
                headers=sf2["headers"],
            )
            assert r.status_code == 201
            report_id_2 = r.json()["id"]

            final2 = await wait_for_status(client, token, report_id_2, "processed", timeout_s=5.0)
            assert final2["status"] == "processed"
            assert final2["ai_output"]["image"]["has_image"] is False
            assert final2["ai_output"]["combined"]["recommendation"].strip() != ""
            assert final2["ai_output"]["models"]["vision"] is None
        finally:
            _pl.chat_json = _real_chat_json_2

        # ---------- AI failure path: status='failed' --------------------------
        # Each pipeline stage already catches OpenAI errors and uses a
        # fallback dict, so a stage-level failure still ends in 'processed'.
        # To exercise the document-level 'failed' path we patch
        # `process_report` itself to raise, simulating a code bug or DB hiccup.
        token2 = await register_citizen(client, "ai_bob@" + "example.com", "AI Bob")
        import app.services.report as _svc
        _real_process_report = _svc.ai_pipeline.process_report

        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated pipeline crash")

        _svc.ai_pipeline.process_report = _boom
        try:
            sf3 = submit_form(
                token2,
                "Something is happening, please send help.",
                with_image=False,
            )
            r = await client.post(
                "/api/report/submit",
                data=sf3["data"],
                headers=sf3["headers"],
            )
            assert r.status_code == 201
            report_id_3 = r.json()["id"]

            failed = await wait_for_status(client, token2, report_id_3, "failed", timeout_s=5.0)
            print("FAILED_STATUS", failed["status"], repr(failed.get("error"))[:80])
            assert failed["status"] == "failed"
            assert failed["error"] is not None
            assert "simulated" in failed["error"].lower()
        finally:
            _svc.ai_pipeline.process_report = _real_process_report

        # ---------- admin reprocess: failed → processed -----------------------
        await seed_admin("admin@" + "example.com")
        admin_token = await login(client, "admin@" + "example.com", "adminpass1")
        fake4 = make_chat_json()
        _real_chat_json_4 = _pl.chat_json
        _pl.chat_json = fake4
        try:
            r = await client.post(
                f"/api/admin/reports/{report_id_3}/reprocess",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            print("ADMIN_REPROCESS", r.status_code)
            assert r.status_code == 200, r.text
            # Admin route awaits the pipeline → status processed immediately.
            assert r.json()["status"] == "processed"
            assert r.json()["ai_output"]["combined"]["type"] == "flood"
        finally:
            _pl.chat_json = _real_chat_json_4

        # Citizens can't hit the admin endpoint.
        r = await client.post(
            f"/api/admin/reports/{report_id_3}/reprocess",
            headers={"Authorization": f"Bearer {token2}"},
        )
        print("ADMIN_REPROCESS_AS_CITIZEN", r.status_code)
        assert r.status_code == 403

        # ---------- recovery sweep -------------------------------------------
        from app.models import report as report_model
        stale = await report_model.create_report(
            user_id="000000000000000000000001",
            payload={
                "description": "A stale report that crashed mid-processing.",
                "location": {"division": "Dhaka"},
                "assistance": [],
                "immediate_danger": False,
            },
            images=[],
        )
        from bson import ObjectId
        cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=120)
        await db_mod._db[report_model.COLLECTION].update_one(
            {"_id": ObjectId(stale["id"])},
            {"$set": {"created_at": cutoff_dt, "updated_at": cutoff_dt}},
        )
        fake5 = make_chat_json()
        _real_chat_json_5 = _pl.chat_json
        _pl.chat_json = fake5
        try:
            from app.services import report as report_service
            recovered = await report_service.recover_pending()
            print("RECOVERED", recovered)
            assert recovered >= 1

            admin_token2 = await login(client, "admin@" + "example.com", "adminpass1")
            final3 = await wait_for_status(
                client, admin_token2, stale["id"], "processed", timeout_s=5.0
            )
            assert final3["status"] == "processed"
            assert final3["ai_output"]["combined"]["type"] == "flood"
        finally:
            _pl.chat_json = _real_chat_json_5

    print("\nALL AI PIPELINE ASSERTIONS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
