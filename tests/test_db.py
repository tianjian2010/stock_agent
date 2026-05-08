import unittest

from services.db import describe_database_settings, resolve_database_settings


class DatabaseSettingsTests(unittest.TestCase):
    def test_resolve_database_settings_requires_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "DATABASE_URL is required"):
            resolve_database_settings(database_url="")

    def test_describe_database_settings_returns_postgres_target(self) -> None:
        settings = resolve_database_settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/stock_agent"
        )
        self.assertEqual(settings.display_name, "PostgreSQL")
        self.assertEqual(
            describe_database_settings(settings),
            "PostgreSQL: postgresql+psycopg://user:pass@localhost:5432/stock_agent",
        )


if __name__ == "__main__":
    unittest.main()
