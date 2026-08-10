#Keeping all application settings in one place, and automatically load them from .env when available
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

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    ranker_path: str = "models/ranker.joblib"


settings = Settings()


#This file is a **configuration file** 
#It uses Pydantic's `BaseSettings` to keep all important application settings in one place and automatically load them from a `.env` file.
# The `Settings` class defines configuration for **MongoDB** (database connection and database name)
#**JWT authentication** (secret key, algorithm, and token expiration), 
#**embedding and reranking models** used for resume-job matching, 
#**LLM APIs** such as Groq and Gemini, and the path to the locally trained ranking model.
# `SettingsConfigDict` tells Pydantic to read the `.env` file using UTF-8 and ignore any extra environment variables that are not defined in the class.
# Finally, `settings = Settings()` creates the actual configuration object, which can be imported anywhere in the application and accessed using values such as `settings.mongodb_uri`, `settings.jwt_secret`, or `settings.embedding_model`. This approach keeps configuration **centralized, reusable, secure, and easy to change between development and production environments**.

