from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = Field(default=3000, alias="PORT")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    fastgpt_base_url: str = Field(default="https://fastgpt.example.com", alias="FASTGPT_BASE_URL")
    fastgpt_api_key: str = Field(default="test_fastgpt_key", alias="FASTGPT_API_KEY")
    dify_base_url: str = Field(default="https://dify.example.com", alias="DIFY_BASE_URL")
    dify_api_key: str = Field(default="test_dify_key", alias="DIFY_API_KEY")

    # LangChain / LangGraph orchestrator (OpenAI-compatible).
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # OpenClaw ClawHub public registry (CLI default: https://clawhub.ai).
    clawhub_registry_url: str = Field(default="https://clawhub.ai", alias="CLAWHUB_REGISTRY_URL")
    # Optional: write skill stub under workspace when registering from ClawHub (TASK-P2-04).
    clawhub_workspace_sync_enabled: bool = Field(default=False, alias="CLAWHUB_WORKSPACE_SYNC_ENABLED")
    clawhub_workspace_path: str = Field(default="", alias="CLAWHUB_WORKSPACE_PATH")


settings = Settings()
