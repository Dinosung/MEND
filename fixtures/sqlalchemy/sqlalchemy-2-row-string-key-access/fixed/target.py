from sqlalchemy import text


def get_user(conn, user_id):
    row = conn.execute(
        text("SELECT id, email, active FROM users WHERE id = :id"), {"id": user_id}
    ).first()
    m = row._mapping
    return {"id": m["id"], "email": m["email"], "active": bool(m["active"])}
