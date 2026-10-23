"""Create consistent, ignored environment files with a generated local password."""

import argparse
from pathlib import Path
import re
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=55432)
    parser.add_argument("--database", default="hissiyat_dev")
    parser.add_argument("--username", default="hissiyat_local")
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535:
        parser.error("The port must be between 1 and 65535.")
    for value in (arguments.database, arguments.username):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
            parser.error("Use lowercase letters, digits and underscores for local identifiers.")
    if arguments.database == "hissiyat_test":
        parser.error("hissiyat_test is reserved for integration tests.")

    root = Path(__file__).resolve().parents[1]
    paths = [root / ".env", root / "backend/.env", root / "backend/.env.test"]
    if any(path.exists() for path in paths):
        parser.error("A local environment file already exists; no files were changed. Edit existing files deliberately.")

    password = secrets.token_urlsafe(32)
    root_content = (
        "# Generated for isolated local development only. Do not publish.\n"
        f"HISSIYAT_POSTGRES_DB={arguments.database}\n"
        f"HISSIYAT_POSTGRES_USER={arguments.username}\n"
        f"HISSIYAT_POSTGRES_PASSWORD={password}\n"
        f"HISSIYAT_POSTGRES_PORT={arguments.port}\n"
    )

    def backend_content(name: str, environment: str) -> str:
        return (
            "# Generated for isolated local development only. Do not publish.\n"
            "HISSIYAT_SERVICE_NAME=Hissiyat API\n"
            f"HISSIYAT_ENVIRONMENT={environment}\n"
            "HISSIYAT_DATABASE_HOST=127.0.0.1\n"
            f"HISSIYAT_DATABASE_PORT={arguments.port}\n"
            f"HISSIYAT_DATABASE_NAME={name}\n"
            f"HISSIYAT_DATABASE_USER={arguments.username}\n"
            f"HISSIYAT_DATABASE_PASSWORD={password}\n"
        )

    contents = [root_content, backend_content(arguments.database, "development"), backend_content("hissiyat_test", "test")]
    for path, content in zip(paths, contents, strict=True):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    print("Created root .env, backend/.env and backend/.env.test. Password was not displayed.")


if __name__ == "__main__":
    main()
