from services import serialize_user


if __name__ == "__main__":
    data = {
        "name": "Анна",
        "email": "anna@example.com",
        "age": 25,
    }

    print(serialize_user(data))
