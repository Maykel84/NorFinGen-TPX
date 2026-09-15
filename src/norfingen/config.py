"""NorFinGen environment configuration — read from .env / system environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    TRIPLETEX_API_BASE_URL: str = os.getenv("TRIPLETEX_API_BASE_URL", "https://tripletex.no/v2")
    TRIPLETEX_CONSUMER_TOKEN: str = os.getenv("TRIPLETEX_CONSUMER_TOKEN", "")
    TRIPLETEX_EMPLOYEE_TOKEN: str = os.getenv("TRIPLETEX_EMPLOYEE_TOKEN", "")
    RENDER_WEBHOOK_URL: str = os.getenv("RENDER_WEBHOOK_URL", "")


settings = Settings()
