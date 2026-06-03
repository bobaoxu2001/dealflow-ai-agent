def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["embedding_provider"] == "local"


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "health" in resp.json()
