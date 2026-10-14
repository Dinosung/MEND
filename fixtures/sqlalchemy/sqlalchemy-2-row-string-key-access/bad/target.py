from sqlalchemy import text


def get_user(conn, user_id):
    row = conn.execute(
        text("SELECT id, email, active FROM users WHERE id = :id"), {"id": user_id}
    ).first()
    return {"id": row["id"], "email": row["email"], "active": bool(row["active"])}
