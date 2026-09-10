from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from funding.api import create_app


def test_entra_checks_signature_audience_and_api_permission(database, monkeypatch):
    cfg, engine, _ = database
    cfg.auth_mode = "entra"
    cfg.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
    cfg.entra_audience = "funding-api"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr("funding.auth.key_client", lambda tenant: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    stamp = datetime.now(UTC)
    claims = dict(iss=f"https://login.microsoftonline.com/{cfg.entra_tenant_id}/v2.0", tid=cfg.entra_tenant_id,
                  oid="reviewer", aud=cfg.entra_audience, iat=stamp, nbf=stamp-timedelta(seconds=1),
                  exp=stamp+timedelta(minutes=5), roles=["Funding.Read"])
    client = TestClient(create_app(cfg, engine))
    token = jwt.encode(claims, key, algorithm="RS256")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/sources", headers=headers).status_code == 200
    assert client.put("/v1/opportunities/missing/review", headers=headers, json={"expected_version": 0, "source_version": 1, "eligibility": "unreviewed"}).status_code == 403
    claims["aud"] = "another-api"
    token = jwt.encode(claims, key, algorithm="RS256")
    assert client.get("/v1/sources", headers={"Authorization": f"Bearer {token}"}).status_code == 401
