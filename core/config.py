from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Pydantic butuh variabel ini didefinisikan agar tidak dianggap 'extra'
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "admin123"
    
    # Tambahkan variabel yang menyebabkan error tadi:
    APP_NAME: str = "Anime Graph API"
    DEBUG: bool = True
    ANILIST_API_URL: str = "https://graphql.anilist.co"
    
    # Konfigurasi agar membaca file .env
    # extra='ignore' akan membuat Pydantic cuek kalau ada variabel lain di .env
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"  
    )

settings = Settings()