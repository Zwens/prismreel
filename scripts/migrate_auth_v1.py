import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.apps.comic_gen import auth_db, user_repo


def _ensure_admin() -> str:
    users = user_repo.list_users()
    admin_users = [u for u in users if u.role == "admin"]
    if admin_users:
        return admin_users[0].id

    email = os.getenv("PRISMREEL_ADMIN_EMAIL", "").strip()
    password = os.getenv("PRISMREEL_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        print("[migrate_auth_v1] ERROR: PRISMREEL_ADMIN_EMAIL and PRISMREEL_ADMIN_PASSWORD must be set for first-run migration.")
        sys.exit(1)

    admin = user_repo.create_user(email, password, role="admin", display_name="Admin")
    print(f"[migrate_auth_v1] Created admin account: {email}")
    return admin.id


def _backfill_owner_id(json_path: str, admin_id: str) -> None:
    if not os.path.exists(json_path):
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    changed = False
    for record in data.values():
        if isinstance(record, dict) and "owner_id" not in record:
            record["owner_id"] = admin_id
            changed = True
    if changed:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[migrate_auth_v1] Backfilled owner_id in {json_path}")


def run() -> None:
    marker = os.path.join("output", ".auth_migrated")
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()

    admin_id = _ensure_admin()

    if not os.path.exists(marker):
        _backfill_owner_id(os.path.join("output", "projects.json"), admin_id)
        _backfill_owner_id(os.path.join("output", "series.json"), admin_id)
        os.makedirs("output", exist_ok=True)
        with open(marker, "w") as f:
            f.write("migrated")
        print("[migrate_auth_v1] Migration complete.")
    else:
        print("[migrate_auth_v1] Already migrated, skipping owner_id backfill.")


if __name__ == "__main__":
    run()
