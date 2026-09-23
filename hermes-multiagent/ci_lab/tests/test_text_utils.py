import unittest

from ci_lab.text_utils import normalize_username


class TextUtilsTests(unittest.TestCase):
    def test_trim_and_lowercase(self):
        self.assertEqual(
            normalize_username("  Alice  "),
            "alice",
        )

    def test_internal_spaces_are_replaced_with_underscore(self):
        self.assertEqual(
            normalize_username("  Alice Smith  "),
            "alice_smith",
        )

    def test_whitespace_groups_do_not_create_repeated_underscores(self):
        self.assertEqual(
            normalize_username("Alice   Smith\tJr"),
            "alice_smith_jr",
        )


if __name__ == "__main__":
    unittest.main()
