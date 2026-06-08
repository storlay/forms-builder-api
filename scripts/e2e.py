"""End-to-end smoke test against a running docker compose stack.

Hits the real container over HTTP (not ASGITransport), exercising the full
happy path: auth -> form lifecycle -> file upload -> submit -> analytics ->
export -> download. Exits non-zero on the first failed expectation.

Run: docker compose up -d --build && uv run python scripts/e2e.py
"""

import csv
import io
import os
import sys
import uuid

import httpx


BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")

FIELDS = [
    {
        "key": "color",
        "type": "single_choice",
        "label": "Color",
        "required": True,
        "options": ["red", "green", "blue"],
    },
    {"key": "tags", "type": "multi_choice", "label": "Tags", "options": ["a", "b", "c"]},
    {"key": "rating", "type": "rating", "label": "Rate", "validation": {"min": 1, "max": 5}},
    {"key": "age", "type": "number", "label": "Age", "validation": {"min": 0, "max": 120}},
    {"key": "bio", "type": "long_text", "label": "Bio"},
    {"key": "doc", "type": "file", "label": "Doc"},
]
FILE_CONTENT = b"resume contents\n" * 50


def expect(r: httpx.Response, code: int) -> httpx.Response:
    if r.status_code != code:
        sys.exit(
            f"FAIL: {r.request.method} {r.request.url.path} -> "
            f"{r.status_code}, want {code}\n{r.text}"
        )
    print(f"ok: {r.request.method} {r.request.url.path} -> {code}")
    return r


def main() -> None:
    # Unique email per run: the prod `forms` db persists on a volume.
    creds = {"email": f"e2e-{uuid.uuid4().hex[:12]}@example.com", "password": "supersecret123"}

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        expect(c.get("/health"), 200)

        expect(c.post("/auth/register", json=creds), 201)
        token = expect(c.post("/auth/login", json=creds), 200).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert expect(c.get("/auth/me", headers=auth), 200).json()["email"] == creds["email"]

        form_id = expect(
            c.post("/forms", json={"title": "E2E Survey", "fields": FIELDS}, headers=auth), 201
        ).json()["id"]
        assert (
            expect(c.post(f"/forms/{form_id}/publish", headers=auth), 200).json()["status"]
            == "published"
        )
        assert len(expect(c.get(f"/f/{form_id}"), 200).json()["fields"]) == len(FIELDS)

        file_id = expect(
            c.post(f"/f/{form_id}/files", files={"file": ("cv.txt", FILE_CONTENT, "text/plain")}),
            201,
        ).json()["file_id"]

        full = {
            "color": "red",
            "tags": ["a", "b"],
            "rating": 5,
            "age": 30,
            "bio": "hello",
            "doc": file_id,
        }
        expect(c.post(f"/f/{form_id}/responses", json={"answers": full}), 201)
        expect(
            c.post(f"/f/{form_id}/responses", json={"answers": {"color": "green", "rating": 3}}),
            201,
        )
        expect(c.post(f"/f/{form_id}/responses", json={"answers": {"color": "purple"}}), 422)
        expect(c.post(f"/f/{form_id}/draft", json={"answers": {"color": "blue"}}), 201)

        assert (
            len(expect(c.get(f"/forms/{form_id}/responses", headers=auth), 200).json()["items"])
            == 2
        )

        analytics = expect(c.get(f"/forms/{form_id}/analytics", headers=auth), 200).json()
        assert analytics["total_responses"] == 2, analytics

        csv_text = expect(
            c.get(f"/forms/{form_id}/export", params={"format": "csv"}, headers=auth), 200
        ).text
        assert len(list(csv.DictReader(io.StringIO(csv_text)))) == 2
        assert (
            len(
                expect(
                    c.get(f"/forms/{form_id}/export", params={"format": "json"}, headers=auth), 200
                ).json()
            )
            == 2
        )

        assert expect(c.get(f"/files/{file_id}"), 200).content == FILE_CONTENT

    print("\nE2E PASSED")


if __name__ == "__main__":
    main()
