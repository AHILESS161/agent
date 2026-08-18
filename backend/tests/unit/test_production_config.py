from app.core.config import Settings


def test_allowed_hosts_accepts_comma_separated_environment_value():
    config = Settings(
        _env_file=None,
        ALLOWED_HOSTS="registr.example.ru,localhost,api",
    )

    assert config.ALLOWED_HOSTS == ["registr.example.ru", "localhost", "api"]


def test_api_docs_can_be_disabled_for_production():
    config = Settings(_env_file=None, API_DOCS_ENABLED="false")

    assert config.API_DOCS_ENABLED is False
