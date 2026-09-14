from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_app_db: str
    postgres_host_port: int = 5433

    minio_endpoint_host_port: str = "localhost:9000"
    minio_root_user: str
    minio_root_password: str
    minio_bucket: str

    keycloak_public_url: str = "http://localhost:8081"
    keycloak_realm: str = "alps-twin"
    keycloak_api_client_id: str = "alps-twin-api"
    # Keycloak issues tokens with `iss` set to whatever Host header the
    # browser used to reach it (no fixed KC_HOSTNAME configured) — direct
    # (8081), through the local gateway (8090), and through the public
    # tunnel are all legitimate ways to reach the SAME Keycloak, so all three
    # issuer forms must validate. See AGENTS.md M7 section.
    keycloak_accepted_issuer_hosts: list[str] = [
        "http://localhost:8081",
        "http://localhost:8090",
        "https://alps-twin.wizbase.ai.kr",
    ]

    # AI assist (M5-lite): any OpenAI-compatible chat endpoint — default is
    # the local Ollama daemon (no key needed); point llm_base_url/llm_api_key
    # at a hosted provider (OpenAI/Upstage/OpenRouter/Gemini-compat) to switch
    # without code changes. Resolution is settings-or-env only, never an
    # ambient login profile, so "not configured" stays testable.
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str | None = None  # hosted providers only; Ollama ignores it
    llm_model: str = "qwen2.5:32b"
    llm_max_tokens: int = 4096
    assistant_max_tool_rounds: int = 5
    assistant_max_messages: int = 40
    assistant_pending_ttl_seconds: int = 900  # 15 min
    # Assistant tools ride the SAME API with the end user's bearer token
    # (loopback), so RBAC/validation/gate-readiness rules are identical.
    internal_api_base_url: str = "http://127.0.0.1:8000"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@localhost:{self.postgres_host_port}/{self.postgres_app_db}"
        )

    @property
    def minio_endpoint_url(self) -> str:
        return f"http://{self.minio_endpoint_host_port}"

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_public_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_accepted_issuers(self) -> list[str]:
        return [f"{host}/realms/{self.keycloak_realm}" for host in self.keycloak_accepted_issuer_hosts]

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"


settings = Settings()
