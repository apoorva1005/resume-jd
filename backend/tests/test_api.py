import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.db as db

mock_client = AsyncMongoMockClient()
db.get_client = lambda: mock_client
db.get_db = lambda: mock_client["test_db"]


class FakeBucket:
    def __init__(self):
        self.files = {}

    async def upload_from_stream(self, filename, data, metadata=None):
        from bson import ObjectId

        file_id = ObjectId()
        self.files[file_id] = data
        return file_id


db.get_bucket = lambda: FakeBucket()


# Import the application after replacing the database functions.
from app.main import app


RESUME_TEXT = b"""Jane Smith
Senior ML Engineer

Skills
Python, PyTorch, FastAPI, MongoDB, scikit-learn, Docker

Experience
Senior ML Engineer at DataCo 2019-2025. 6 years building retrieval systems,
RAG pipelines and recommendation models that served production traffic.

Education
MS Computer Science, Tech University
"""

JOB_DESCRIPTION = """Backend ML Engineer. We need Python, FastAPI, vector databases
and 5+ years of experience. Bachelors degree required. Experience with RAG
and retrieval systems strongly preferred."""

TEST_EMAIL = "jane@example.com"
TEST_PASSWORD = "hunter2hunter2"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def token(client):
    response = client.post(
        "/auth/signup",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 201

    return response.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_check(client):
    response = client.get("/health")
    assert response.json()["status"] == "ok"


def test_duplicate_signup_is_rejected(client, token):
    response = client.post(
        "/auth/signup",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 409


def test_login_with_wrong_password_fails(client, token):
    response = client.post(
        "/auth/login",
        data={
            "username": TEST_EMAIL,
            "password": "wrong-pass",
        },
    )

    assert response.status_code == 401


def test_protected_routes_require_authentication(client):
    assert client.get("/resumes").status_code == 401

    response = client.get(
        "/resumes",
        headers=auth_header("garbage.token.here"),
    )

    assert response.status_code == 401


def test_get_current_user(client, token):
    response = client.get(
        "/auth/me",
        headers=auth_header(token),
    )

    assert response.json()["email"] == TEST_EMAIL


def test_complete_matching_flow(client, token):
    resume_response = client.post(
        "/resumes",
        headers=auth_header(token),
        files={
            "file": (
                "resume.txt",
                RESUME_TEXT,
                "text/plain",
            )
        },
    )

    assert resume_response.status_code == 201, resume_response.text
    resume_id = resume_response.json()["id"]

    jd_response = client.post(
        "/jds",
        headers=auth_header(token),
        data={"text": JOB_DESCRIPTION},
    )

    assert jd_response.status_code == 201, jd_response.text
    jd_id = jd_response.json()["id"]

    match_response = client.post(
        "/matches",
        headers=auth_header(token),
        json={
            "resume_id": resume_id,
            "jd_id": jd_id,
        },
    )

    assert match_response.status_code == 201, match_response.text

    match = match_response.json()

    assert 0.0 <= match["final_score"] <= 1.0
    assert 0.0 <= match["cosine_score"] <= 1.0
    assert match["explanation_text"]

    expected_features = {
        "cosine_score",
        "cross_encoder_score",
        "keyword_overlap",
        "years_match",
        "education_match",
    }

    assert set(match["features"]) == expected_features
    assert match["features"]["years_match"] == 1.0
    assert match["features"]["education_match"] == 1.0

    matches_response = client.get(
        "/matches",
        headers=auth_header(token),
    )

    assert len(matches_response.json()) == 1


def test_users_cannot_access_each_others_data(client, token):
    other_user_response = client.post(
        "/auth/signup",
        json={
            "email": "bob@example.com",
            "password": TEST_PASSWORD,
        },
    )

    other_token = other_user_response.json()["access_token"]

    assert client.get(
        "/resumes",
        headers=auth_header(other_token),
    ).json() == []

    assert client.get(
        "/matches",
        headers=auth_header(other_token),
    ).json() == []

    jane_resumes = client.get(
        "/resumes",
        headers=auth_header(token),
    ).json()

    jane_jds = client.get(
        "/jds",
        headers=auth_header(token),
    ).json()

    jane_resume_id = jane_resumes[0]["id"]
    jane_jd_id = jane_jds[0]["id"]

    stolen_match = client.post(
        "/matches",
        headers=auth_header(other_token),
        json={
            "resume_id": jane_resume_id,
            "jd_id": jane_jd_id,
        },
    )

    assert stolen_match.status_code == 404

    jane_matches = client.get(
        "/matches",
        headers=auth_header(token),
    ).json()

    jane_match_id = jane_matches[0]["id"]

    response = client.get(
        f"/matches/{jane_match_id}",
        headers=auth_header(other_token),
    )

    assert response.status_code == 404


def test_invalid_uploads_are_rejected(client, token):
    empty_file = client.post(
        "/resumes",
        headers=auth_header(token),
        files={
            "file": (
                "empty.txt",
                b"",
                "text/plain",
            )
        },
    )

    assert empty_file.status_code == 400

    unsupported_file = client.post(
        "/resumes",
        headers=auth_header(token),
        files={
            "file": (
                "image.jpg",
                b"\xff\xd8\xff" * 40,
                "image/jpeg",
            )
        },
    )

    assert unsupported_file.status_code == 400

    empty_jd = client.post(
        "/jds",
        headers=auth_header(token),
        data={"text": ""},
    )

    assert empty_jd.status_code == 400
