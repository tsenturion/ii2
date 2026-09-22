from pydantic import BaseModel, field_validator


class User(BaseModel):
    name: str
    email: str
    age: int

    @field_validator("age")
    @classmethod
    def validate_age(cls, value):
        if value < 18:
            raise ValueError("Возраст должен быть не меньше 18 лет")
        return value
