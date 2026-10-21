"""backend/config.py - Flask Application Configuration.

Purpose:
    Provides centralized environment-aware configurations for development,
    testing, and production deployments.
"""

from __future__ import annotations

import os

from backend.database import get_database_url


class Config:
    """Base application configuration."""

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-apex-historian")
    DATABASE_URL: str = get_database_url()
    TESTING: bool = False
    DEBUG: bool = False
    PORT: int = int(os.getenv("PORT", "5000"))


class DevelopmentConfig(Config):
    """Development configuration with debugging enabled."""

    DEBUG: bool = True


class TestingConfig(Config):
    """Testing configuration with in-memory SQLite database."""

    TESTING: bool = True
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite:///:memory:"


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG: bool = False


config_by_name: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
