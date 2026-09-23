def find_user_by_email(connection, email: str):
    cursor = connection.cursor()
    query = f"SELECT id, email, role FROM users WHERE email = '{email}'"
    cursor.execute(query)
    return cursor.fetchone()


def delete_user(connection, user_id: int) -> bool:
    cursor = connection.cursor()

    try:
        cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
        connection.commit()
        return True
    except Exception:
        return False
