#Keeping all application settings in one place
#automatically load them from .env when available
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "resume_matcher"

    jwt_secret: str = "dev-secret-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    embedding_dim: int = 384

    # Chroma is the vector index. Mongo stays the durable source of truth for
    # documents and their vectors; Chroma is what answers similarity queries.
    #   memory     -> in-process, nothing on disk (tests)
    #   persistent -> local directory, no server needed (non-Docker dev)
    #   http       -> a Chroma server (docker compose sets this)
    chroma_mode: str = "persistent"
    chroma_path: str = "./chroma_data"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    chroma_ssl: bool = False
    chroma_resume_collection: str = "resume_embeddings"
    chroma_jd_collection: str = "jd_embeddings"

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    ranker_path: str = "models/ranker.joblib"


settings = Settings()
