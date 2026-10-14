def test_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/prod")
    monkeypatch.setenv("DEBUG", "true")
    import target

    settings = target.load_settings()
    assert settings.database_url == "postgresql://db/prod"
    assert settings.debug is True
