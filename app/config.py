from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Voice SRE Agentic Supervisor"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Kubernetes Settings
    KUBERNETES_USE_MOCK: bool = True  # Default to True for development without cluster
    
    # Prometheus Settings
    PROMETHEUS_URL: str = "http://localhost:9090"
    
    # OpenAI/Anthropic/LiveKit Settings (Placeholder for future phases)
    OPENAI_API_KEY: str = ""
    LIVEKIT_API_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Auto-detect if Kubernetes cluster is available; if not, force mock mode
if not settings.KUBERNETES_USE_MOCK:
    try:
        from kubernetes import config
        # Try loading kube_config, if it fails, try in_cluster
        try:
            config.load_kube_config()
        except Exception:
            try:
                config.load_incluster_config()
            except Exception:
                # Force mock if no config found
                settings.KUBERNETES_USE_MOCK = True
    except ImportError:
        settings.KUBERNETES_USE_MOCK = True
