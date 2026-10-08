"""Unit tests for the API-fetching logic. The real API is replaced by a fake session."""

import pytest
import requests

import load_hdb_resale


class FakeResponse:
    def __init__(self, status_code: int, result: dict | None = None):
        self.status_code = status_code
        self._result = result

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> dict:
        return {"result": self._result}


class FakeSession:
    """Stands in for requests.Session: returns queued responses and records each request's params."""

    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.requested_params: list[dict] = []

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.requested_params.append(params)
        return self.responses.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def page(records: list[dict], total: int) -> FakeResponse:
    return FakeResponse(200, {"records": records, "total": total})


def use_fake_session(monkeypatch, responses: list[FakeResponse]) -> FakeSession:
    session = FakeSession(responses)
    monkeypatch.setattr(load_hdb_resale.requests, "Session", lambda: session)
    return session


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip the polite pauses and backoff waits so tests run instantly."""
    monkeypatch.setattr(load_hdb_resale.time, "sleep", lambda seconds: None)


def test_fetches_all_pages_until_empty_page(monkeypatch):
    session = use_fake_session(
        monkeypatch,
        [
            page([{"_id": 1}, {"_id": 2}], total=3),
            page([{"_id": 3}], total=3),
            page([], total=3),
        ],
    )

    records = load_hdb_resale.fetch_all_records("resource-id")

    assert [r["_id"] for r in records] == [1, 2, 3]
    # Offset advances by rows actually received, not by PAGE_SIZE
    assert [p["offset"] for p in session.requested_params] == [0, 2, 3]


def test_raises_when_rows_are_missing(monkeypatch):
    use_fake_session(monkeypatch, [page([{"_id": 1}], total=3), page([], total=3)])

    with pytest.raises(RuntimeError, match="Expected 3 rows but fetched 1"):
        load_hdb_resale.fetch_all_records("resource-id")


def test_retries_after_rate_limit(monkeypatch):
    session = use_fake_session(
        monkeypatch,
        [FakeResponse(429), page([{"_id": 1}], total=1), page([], total=1)],
    )

    records = load_hdb_resale.fetch_all_records("resource-id")

    assert len(records) == 1
    assert len(session.requested_params) == 3  # 429, retry, empty page


def test_gives_up_after_max_retries(monkeypatch):
    use_fake_session(monkeypatch, [FakeResponse(429)] * load_hdb_resale.MAX_RETRIES)

    with pytest.raises(requests.HTTPError):
        load_hdb_resale.fetch_all_records("resource-id")


def test_other_errors_fail_without_retrying(monkeypatch):
    session = use_fake_session(monkeypatch, [FakeResponse(500)])

    with pytest.raises(requests.HTTPError):
        load_hdb_resale.fetch_all_records("resource-id")
    assert len(session.requested_params) == 1
