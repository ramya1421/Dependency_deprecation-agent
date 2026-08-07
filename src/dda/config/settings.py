from pydantic_settings import BaseSettings, SettingsConfigDict

from dda.application.services.risk_scoring_service import DEFAULT_RISK_WEIGHTS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    github_token: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    database_path: str = "dda.db"
    log_level: str = "INFO"

    risk_weight_deprecation: float = DEFAULT_RISK_WEIGHTS["deprecation"]
    risk_weight_vulnerability: float = DEFAULT_RISK_WEIGHTS["vulnerability"]
    risk_weight_abandonment: float = DEFAULT_RISK_WEIGHTS["abandonment"]
    risk_weight_eol: float = DEFAULT_RISK_WEIGHTS["eol"]
    risk_weight_major_versions_behind: float = DEFAULT_RISK_WEIGHTS["major_versions_behind"]

    @property
    def risk_weights(self) -> dict[str, float]:
        return {
            "deprecation": self.risk_weight_deprecation,
            "vulnerability": self.risk_weight_vulnerability,
            "abandonment": self.risk_weight_abandonment,
            "eol": self.risk_weight_eol,
            "major_versions_behind": self.risk_weight_major_versions_behind,
        }
