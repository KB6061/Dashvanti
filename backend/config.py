from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str
    jwt_secret: str = Field(min_length=32)
    kafka_bootstrap_servers: str = 'kafka:9092'
    file_root: str = '/opt/dashvanti_fs'
    public_url: str = 'http://localhost:8000'
    smtp_host: str = 'mailpit'
    smtp_port: int = 1025
    smtp_tls: bool = False
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_from: str = 'noreply@dashvanti.local'
    admin_secret: str = Field(default='', validation_alias='ADMIN_PASSWORD')

settings = Settings()
