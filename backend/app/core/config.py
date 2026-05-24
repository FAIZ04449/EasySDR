import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "EasySDR Engine"
    DATABASE_URL: str = "sqlite:///./prospecting.db"
    
    # API Configurations
    APOLLO_API_KEY: Optional[str] = None
    HUBSPOT_ACCESS_TOKEN: Optional[str] = None
    
    # Datanyze & ZoomInfo Configurations
    DATANYZE_API_KEY: Optional[str] = None
    ZOOMINFO_API_KEY: Optional[str] = None
    
    # Kimi Code AI config (OpenAI-compatible)
    KIMI_API_KEY: Optional[str] = None
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k" # Default Kimi model
    
    # LinkedIn Authentication (for Playwright crawler)
    LINKEDIN_USERNAME: Optional[str] = None
    LINKEDIN_PASSWORD: Optional[str] = None
    LINKEDIN_COOKIES_JSON: Optional[str] = None  # JSON string of cookies block
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
