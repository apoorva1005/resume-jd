import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import app.db as db
from app.config import settings

settings.chroma_mode = "memory"
settings.chroma_resume_collection = "test_resume_embeddings"
settings.chroma_jd_collection = "test_jd_embeddings"

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

# A deliberately unrelated resume, so vector search has something it should
# rank *below* the ML one rather than just returning everything it holds.
NURSE_RESUME = b"""Mary Jones
Registered Nurse

Skills
Patient care, triage, phlebotomy, electronic health records

Experience
Staff nurse at County Hospital. 2 years on a general medical ward providing
bedside care, medication administration and discharge planning.

Education
Bachelors of Nursing, City College
"""


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
    payload = response.json()

    assert payload["status"] == "ok"
    vector_store = payload["vector_store"]
    assert vector_store["mode"] == "memory"
    assert vector_store["connected"] is True


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
    # Upload a resume first.
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

    # Create the job description.
    jd_response = client.post(
        "/jds",
        headers=auth_header(token),
        data={"text": JOB_DESCRIPTION},
    )

    assert jd_response.status_code == 201, jd_response.text
    jd_id = jd_response.json()["id"]

    # Match the resume against the job description.
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

    # Bob should start with an empty account.
    assert client.get(
        "/resumes",
        headers=auth_header(other_token),
    ).json() == []

    assert client.get(
        "/matches",
        headers=auth_header(other_token),
    ).json() == []

    # Get Jane's document IDs.
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

    # Bob should not be able to use Jane's documents.
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

    # Bob also cannot access Jane's match.
    response = client.get(
        f"/matches/{jane_match_id}",
        headers=auth_header(other_token),
    )

    assert response.status_code == 404


def test_invalid_uploads_are_rejected(client, token):
    # Empty files should not be accepted.
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

    # Unsupported file types should also be rejected.
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

    # An empty job description should fail validation.
    empty_jd = client.post(
        "/jds",
        headers=auth_header(token),
        data={"text": ""},
    )

    assert empty_jd.status_code == 400


# --- Vector search -------------------------------------------------------
# These run against a real in-memory Chroma (see settings.chroma_mode above),
# so ranking and metadata filtering are actually executed rather than mocked.


@pytest.fixture(scope="module")
def indexed_documents(client, token):
    nurse = client.post(
        "/resumes",
        headers=auth_header(token),
        files={"file": ("nurse.txt", NURSE_RESUME, "text/plain")},
    )
    assert nurse.status_code == 201, nurse.text
    assert nurse.json()["indexed"] is True, "upload did not reach Chroma"

    resumes_list = client.get("/resumes", headers=auth_header(token)).json()
    jds_list = client.get("/jds", headers=auth_header(token)).json()

    ml_resume = next(r for r in resumes_list if "Jane Smith" in r["preview"])

    return {
        "ml_resume_id": ml_resume["id"],
        "nurse_resume_id": nurse.json()["id"],
        "jd_id": jds_list[0]["id"],
    }


def search_resumes(client, token, **body):
    return client.post(
        "/search/resumes", headers=auth_header(token), json=body
    )


def test_vector_stats_counts_only_your_own(client, token, indexed_documents):
    stats = client.get("/search/stats", headers=auth_header(token)).json()

    assert stats["mode"] == "memory"
    assert stats["resume_vectors"] == 2  # Jane's ML resume + the nursing one
    assert stats["jd_vectors"] == 1


def test_listing_reports_index_state(client, token, indexed_documents):
    """`indexed` comes back on the list path, not just the upload response."""
    resumes_list = client.get("/resumes", headers=auth_header(token)).json()

    assert resumes_list, "expected at least one resume"
    assert all(doc["indexed"] is True for doc in resumes_list)


def test_search_ranks_the_relevant_resume_first(client, token, indexed_documents):
    """The ML resume should out-rank the nursing one against an ML job."""
    response = search_resumes(
        client, token, query_id=indexed_documents["jd_id"], k=5
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["searched_kind"] == "resume"
    assert payload["query_kind"] == "jd"
    assert payload["count"] == 2

    hits = payload["hits"]
    assert hits[0]["id"] == indexed_documents["ml_resume_id"]
    # Ranked, not merely returned: strictly better, and the metadata came back.
    assert hits[0]["similarity"] > hits[1]["similarity"]
    assert 0.0 <= hits[1]["similarity"] <= 1.0
    assert hits[0]["years_experience"] == 6
    assert hits[0]["preview"]


def test_search_accepts_raw_text_as_the_query(client, token, indexed_documents):
    response = search_resumes(
        client,
        token,
        query_text="Looking for a nurse to provide bedside patient care.",
        k=2,
    )

    assert response.status_code == 200, response.text
    hits = response.json()["hits"]

    # Query embedded on the fly; the nursing resume should now come first.
    assert hits[0]["id"] == indexed_documents["nurse_resume_id"]


def test_metadata_filter_excludes_before_ranking(client, token, indexed_documents):
    """min_years is a Chroma pre-filter, so k applies to what survives it."""
    response = search_resumes(
        client,
        token,
        query_id=indexed_documents["jd_id"],
        k=5,
        filters={"min_years": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    # Jane claims 6 years, the nurse 2 -- so only one document is eligible.
    assert payload["count"] == 1
    assert payload["hits"][0]["id"] == indexed_documents["ml_resume_id"]

    # The response says which conditions were applied, including the owner scope.
    assert any("years_experience gte 5" in f for f in payload["filters_applied"])
    assert any("user_id" in f for f in payload["filters_applied"])


def test_degree_filter_uses_the_same_ranking_as_the_scorer(
    client, token, indexed_documents
):
    """degree_rank 2 = masters; the nursing resume only reaches bachelors."""
    masters_only = search_resumes(
        client,
        token,
        query_id=indexed_documents["jd_id"],
        filters={"min_degree_rank": 2},
    ).json()

    assert [h["id"] for h in masters_only["hits"]] == [
        indexed_documents["ml_resume_id"]
    ]

    bachelors_up = search_resumes(
        client,
        token,
        query_id=indexed_documents["jd_id"],
        filters={"min_degree_rank": 1},
    ).json()

    assert bachelors_up["count"] == 2


def test_document_filter_requires_a_literal_term(client, token, indexed_documents):
    """must_contain is a where_document filter over the indexed text."""
    response = search_resumes(
        client,
        token,
        query_id=indexed_documents["jd_id"],
        filters={"must_contain": "phlebotomy"},
    )

    payload = response.json()

    # Only the nursing resume contains the word, even though the ML resume is
    # the closer vector match -- the filter wins.
    assert payload["count"] == 1
    assert payload["hits"][0]["id"] == indexed_documents["nurse_resume_id"]


def test_search_jds_runs_the_other_direction(client, token, indexed_documents):
    response = client.post(
        "/search/jds",
        headers=auth_header(token),
        json={"query_id": indexed_documents["ml_resume_id"], "k": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["searched_kind"] == "jd"
    assert payload["query_kind"] == "resume"
    assert [h["id"] for h in payload["hits"]] == [indexed_documents["jd_id"]]


def test_search_is_isolated_between_users(client, token, indexed_documents):
    bob = client.post(
        "/auth/signup",
        json={"email": "carol@example.com", "password": TEST_PASSWORD},
    ).json()["access_token"]

    # Bob's own view of the index is empty.
    bob_stats = client.get("/search/stats", headers=auth_header(bob)).json()
    assert bob_stats["resume_vectors"] == 0
    assert bob_stats["jd_vectors"] == 0

    # Text that matches Jane's resume closely still finds nothing for Bob.
    bob_search = search_resumes(
        client, bob, query_text="Senior ML engineer with Python and PyTorch.", k=10
    )
    assert bob_search.status_code == 200, bob_search.text
    assert bob_search.json()["hits"] == []

    # And he cannot use Jane's JD as the query vector.
    stolen = search_resumes(client, bob, query_id=indexed_documents["jd_id"])
    assert stolen.status_code == 404


def test_search_rejects_a_query_with_no_input(client, token):
    assert search_resumes(client, token).status_code == 400
    assert search_resumes(client, token, query_id="not-an-object-id").status_code == 400
