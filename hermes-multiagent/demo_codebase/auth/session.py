def create_session(user_id: int) -> dict:
    """Создаёт пользовательскую сессию."""

    return {
        "user_id": user_id,
        "active": True,
    }
