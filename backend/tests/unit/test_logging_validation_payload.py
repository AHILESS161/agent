from app.core.logging import mask_sensitive_data


def test_numeric_keys_in_model_validation_errors_do_not_break_fallback():
    result = mask_sensitive_data(None, "warning", {
        "validation": {0: {"email": "user@example.test", "password": "private"}},
    })
    assert result["validation"][0] == {"email": "***@example.test", "password": "***"}
