import asyncio

import pytest
from fastapi import HTTPException

from app import main
from app.security import CurrentUser, Role


USER = CurrentUser(uid="pi-test-user", username="test", role=Role.VIEWER)


def payment(**changes):
    value = {
        "user_uid": USER.uid, "direction": "user_to_app", "network": "Pi Testnet",
        "amount": 0.01, "metadata": {"purpose": "trace_ai_test"},
        "status": {"developer_approved": False, "transaction_verified": True,
                   "developer_completed": False, "cancelled": False, "user_cancelled": False},
        "transaction": {"txid": "verifiedtx", "verified": True},
    }
    value.update(changes)
    return value


def test_wrong_user_cannot_approve(monkeypatch):
    monkeypatch.setenv("PI_TEST_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PI_API_KEY", "test-only")
    async def pi_api(*args, **kwargs):
        return payment(user_uid="someone-else")
    monkeypatch.setattr(main, "_pi_payment", pi_api)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.approve_test_payment(main.PiPaymentRequest(payment_id="payment1"), USER))
    assert exc.value.status_code == 403


def test_transaction_must_match_verified_pi_payment(monkeypatch):
    monkeypatch.setenv("PI_TEST_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PI_API_KEY", "test-only")
    async def pi_api(*args, **kwargs):
        return payment()
    monkeypatch.setattr(main, "_pi_payment", pi_api)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.complete_test_payment(main.PiPaymentRequest(payment_id="payment1", txid="wrong"), USER))
    assert exc.value.status_code == 409


def test_valid_approval_and_completion(monkeypatch):
    monkeypatch.setenv("PI_TEST_PAYMENT_ENABLED", "true")
    monkeypatch.setenv("PI_API_KEY", "test-only")
    calls = []
    async def pi_api(method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/complete"):
            return payment(status={"developer_completed": True})
        return payment()
    monkeypatch.setattr(main, "_pi_payment", pi_api)
    assert asyncio.run(main.approve_test_payment(main.PiPaymentRequest(payment_id="payment1"), USER)) == {"status": "approved"}
    assert asyncio.run(main.complete_test_payment(main.PiPaymentRequest(payment_id="payment1", txid="verifiedtx"), USER)) == {"status": "completed"}
    assert ("POST", "payment1/approve", {}) in calls
    assert ("POST", "payment1/complete", {"txid": "verifiedtx"}) in calls
