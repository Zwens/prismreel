import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_migration_creates_admin_and_marker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRISMREEL_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("PRISMREEL_ADMIN_PASSWORD", "testpassword123")
    os.makedirs("output", exist_ok=True)
    with open("output/projects.json", "w") as f:
        json.dump({"proj-1": {"id": "proj-1", "title": "Old Project"}}, f)

    import importlib
    from src.apps.comic_gen import auth_db, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", os.path.join(str(tmp_path), "output", "auth.db"))
    importlib.reload(user_repo)

    import scripts.migrate_auth_v1 as migrate
    importlib.reload(migrate)
    migrate.run()

    assert os.path.exists("output/.auth_migrated")
    users = user_repo.list_users()
    assert len(users) == 1
    assert users[0].role == "admin"

    with open("output/projects.json") as f:
        data = json.load(f)
    assert data["proj-1"]["owner_id"] == users[0].id


def test_migration_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRISMREEL_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("PRISMREEL_ADMIN_PASSWORD", "testpassword123")
    os.makedirs("output", exist_ok=True)
    with open("output/projects.json", "w") as f:
        json.dump({}, f)

    import importlib
    from src.apps.comic_gen import auth_db, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", os.path.join(str(tmp_path), "output", "auth.db"))
    importlib.reload(user_repo)

    import scripts.migrate_auth_v1 as migrate
    importlib.reload(migrate)
    migrate.run()
    migrate.run()

    assert len(user_repo.list_users()) == 1


def test_migration_requires_admin_env_vars(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRISMREEL_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("PRISMREEL_ADMIN_PASSWORD", raising=False)
    os.makedirs("output", exist_ok=True)

    import importlib
    from src.apps.comic_gen import auth_db
    monkeypatch.setattr(auth_db, "_DB_PATH", os.path.join(str(tmp_path), "output", "auth.db"))

    import scripts.migrate_auth_v1 as migrate
    importlib.reload(migrate)

    import pytest
    with pytest.raises(SystemExit):
        migrate.run()
