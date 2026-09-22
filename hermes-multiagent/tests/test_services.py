import unittest

from pydantic import ValidationError

from services import serialize_user


class UserServiceTests(unittest.TestCase):
    def test_valid_user(self):
        data = {
            "name": "Анна",
            "email": "anna@example.com",
            "age": 25,
        }

        self.assertEqual(serialize_user(data), data)

    def test_minor_user_rejected(self):
        data = {
            "name": "Иван",
            "email": "ivan@example.com",
            "age": 16,
        }

        with self.assertRaises(ValidationError):
            serialize_user(data)


if __name__ == "__main__":
    unittest.main()
