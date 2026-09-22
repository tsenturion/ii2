from models import User


def serialize_user(data: dict) -> dict:
    user = User.model_validate(data)
    return user.model_dump()
