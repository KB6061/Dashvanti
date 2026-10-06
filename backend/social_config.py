from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SocialSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    social_origin: str = 'https://customer.dashvanti.com'
    google_client_id: str = ''
    facebook_app_id: str = ''
    facebook_app_secret: str = ''
    facebook_graph_version: str = Field(default='', pattern=r'^(v\d+\.\d+)?$')
    social_token_minutes: int = Field(default=15, ge=5, le=60)


social_settings = SocialSettings()
