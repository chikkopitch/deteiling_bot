def test_application_modules_import() -> None:
    import app.main
    import app.models

    assert app.main.main is not None
    assert app.models.User is not None
