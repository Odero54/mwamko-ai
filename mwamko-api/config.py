# Load environment variables from the .env file
load_dotenv(override=True)


class Settings:
    """Class to hold application settings loaded from environment variables."""

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
    )

    # JWT Settings (for future use)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "jwt_key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    # AI Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "openai")
    AI_MODEL: str = "gpt-4"
    ENABLE_AI_AGENTS: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
