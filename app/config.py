from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str
    data_dir: str


settings = Settings()