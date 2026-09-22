from pydantic import BaseModel, field_validator


class Product(BaseModel):
    name: str
    price: float

    @field_validator("price")
    @classmethod
    def validate_price(cls, value):
        if value <= 0:
            raise ValueError("Цена должна быть больше нуля")
        return value


def create_product(data: dict) -> dict:
    product = Product.model_validate(data)
    return product.model_dump()
