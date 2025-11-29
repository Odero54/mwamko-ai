import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv(override=True)

class Settings:
    """Class to hold application settings loaded from environment variables."""
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://mwamko:mwamkoai2025@localhost:5432/mwamko_db")
    
    # JWT Settings (for future use)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "a6fe0dba82bb8ce804b8718e5dce64023b8d39fece62410e5b56e626dfc9c9c9")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    # AI Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "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")
    AI_MODEL: str = "gpt-4"
    ENABLE_AI_AGENTS: bool = True

    class Config:
        env_file = "../mwamkoapp/.env"

settings = Settings()