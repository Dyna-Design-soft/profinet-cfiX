from cfix_api.gui import auth


def test_verify_password_before_any_file_exists_uses_default(tmp_path):
    auth_path = tmp_path / "auth.json"
    assert not auth_path.exists()
    assert auth.verify_password(auth.DEFAULT_PASSWORD, auth_path) is True
    assert auth.verify_password("wrong", auth_path) is False


def test_ensure_password_set_creates_default_and_is_idempotent(tmp_path):
    auth_path = tmp_path / "auth.json"
    auth.ensure_password_set(auth_path)
    assert auth_path.exists()
    assert auth.verify_password(auth.DEFAULT_PASSWORD, auth_path) is True

    # Calling again must not reset a since-changed password back to default.
    auth.set_password("changed", auth_path)
    auth.ensure_password_set(auth_path)
    assert auth.verify_password("changed", auth_path) is True
    assert auth.verify_password(auth.DEFAULT_PASSWORD, auth_path) is False


def test_set_password_then_verify(tmp_path):
    auth_path = tmp_path / "auth.json"
    auth.set_password("hunter2", auth_path)
    assert auth.verify_password("hunter2", auth_path) is True
    assert auth.verify_password("wrong", auth_path) is False
    assert auth.verify_password("", auth_path) is False


def test_password_hash_not_stored_in_plaintext(tmp_path):
    auth_path = tmp_path / "auth.json"
    auth.set_password("hunter2", auth_path)
    contents = auth_path.read_text()
    assert "hunter2" not in contents
