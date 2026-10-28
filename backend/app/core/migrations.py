"""Safety checks for explicit local migration commands; never used at API startup."""

from pathlib import Path

from psycopg import Connection as PsycopgConnection
from psycopg.pq import ConnStatus
from sqlalchemy import Connection, Index, UniqueConstraint, text

from app.core.config import Settings
from app.core.schema import metadata

INITIAL_REVISION = "0001_text_foundation"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class MigrationSafetyError(ValueError):
    """Fail without including credentials, input content or driver error details."""


def migration_settings(target: str | None) -> Settings:
    if target not in {"test", "development"}:
        raise MigrationSafetyError("Choose an explicit target: test or development.")
    settings = Settings(_env_file=BACKEND_ROOT / (".env.test" if target == "test" else ".env"))
    validate_target(settings, target)
    return settings


def validate_target(settings: Settings, target: str) -> None:
    expected = {"test": "hissiyat_test", "development": "hissiyat_dev"}.get(target)
    if (
        expected is None or not settings.database_is_configured
        or settings.database_name != expected or settings.environment != target
        or settings.database_host != "127.0.0.1" or settings.database_port != 55432
    ):
        raise MigrationSafetyError("Migration target must match the isolated local Hissiyat configuration.")


def validate_operation(operation: str, target: str, allow_development: bool = False) -> None:
    if operation not in {"upgrade", "current", "check"}:
        raise MigrationSafetyError("Only upgrade, current and check are supported online in this phase.")
    if operation == "upgrade" and target == "development" and not allow_development:
        raise MigrationSafetyError("Development upgrade requires explicit approval and allow_development=true.")


def validate_connection_target(connection: Connection, settings: Settings) -> None:
    """Check the connected driver's destination, not an engine URL or server identity."""
    validate_target(settings, settings.environment)
    try:
        if connection.closed is not False or connection.invalidated is not False:
            raise MigrationSafetyError("Migration connection must be open and valid.")
        if connection.in_transaction() is not True:
            raise MigrationSafetyError("Migration connection requires an explicit active transaction.")
        if connection.dialect.name != "postgresql" or connection.dialect.driver != "psycopg":
            raise MigrationSafetyError("Migration connection requires the synchronous psycopg driver.")
        driver = connection.connection.driver_connection
        if (
            not isinstance(driver, PsycopgConnection)
            or driver.closed is not False or driver.broken is not False
            or driver.pgconn.status != ConnStatus.OK
        ):
            raise MigrationSafetyError("Migration driver connection is unavailable or unsupported.")
        info = driver.info
        destination = (info.host, info.hostaddr, info.port, info.dbname)
    except MigrationSafetyError:
        raise
    except Exception:
        # Metadata access can raise driver errors containing private connection data.
        raise MigrationSafetyError("Migration connection destination metadata could not be verified.") from None

    if (
        tuple(type(value) for value in destination) != (str, str, int, str)
        or destination != (
            settings.database_host, settings.database_host,
            settings.database_port, settings.database_name,
        )
    ):
        raise MigrationSafetyError("Migration connection destination does not match the authorized target.")


def inspect_migration_state(connection: Connection, expected_database: str) -> str:
    if connection.dialect.name != "postgresql":
        raise MigrationSafetyError("Only PostgreSQL is supported for these migrations.")
    if connection.execute(text("SELECT current_database()")).scalar_one() != expected_database:
        raise MigrationSafetyError("Connected database does not match the selected target.")
    connection.execute(text("SET LOCAL search_path TO public"))
    objects = set(connection.execute(text(
        "SELECT n.nspname,c.relname,c.relkind FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname !~ '^pg_'"
    )))
    extras = connection.execute(text(
        "SELECT (SELECT count(*) FROM pg_namespace WHERE nspname NOT IN "
        "('public','information_schema') AND nspname !~ '^pg_') + "
        "(SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql') + "
        "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='public') + "
        "(SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname='public' AND t.typtype IN ('d','e','r','m')) + "
        "(SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal)"
    )).scalar_one()
    if extras:
        raise MigrationSafetyError("Unexpected schema objects exist; inspect manually before migrating.")
    if not objects:
        return "empty"
    expected = {("public", table.name, "r") for table in metadata.tables.values()}
    expected |= {("public", "alembic_version", "r"), ("public", "alembic_version_pkc", "i")}
    for table in metadata.tables.values():
        expected |= {("public", item.name, "i") for item in [table.primary_key, *table.constraints, *table.indexes]
                     if item.name and (item is table.primary_key or isinstance(item, (UniqueConstraint, Index)))}
    if objects != expected:
        raise MigrationSafetyError("Unexpected or incomplete database objects exist; no automatic repair is allowed.")
    revisions = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
    if revisions != [INITIAL_REVISION]:
        raise MigrationSafetyError("Unexpected migration history; no automatic stamping or reset is allowed.")
    return INITIAL_REVISION
