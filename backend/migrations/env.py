"""Explicit, guarded Alembic execution using the existing SQLAlchemy Core pool."""

from alembic import context
from alembic.util import CommandError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import Database
from app.core.migrations import (
    MigrationSafetyError, inspect_migration_state, migration_settings,
    validate_connection_target, validate_operation,
)
from app.core.schema import metadata

config = context.config
arguments = context.get_x_argument(as_dictionary=True)
target = config.attributes.get("target", arguments.get("target"))
command = getattr(config.cmd_opts, "cmd", None)
operation = config.attributes.get("operation", command[0].__name__ if command else "")
allow_development = arguments.get("allow_development") == "true"


def run_on_connection(connection, settings):
    validate_connection_target(connection, settings)
    inspect_migration_state(connection, settings.database_name)
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


try:
    settings = migration_settings(target)
    validate_operation(operation, target, allow_development)
    if context.is_offline_mode():
        context.configure(dialect_name="postgresql", target_metadata=metadata, literal_binds=True)
        with context.begin_transaction():
            context.execute("SET LOCAL search_path TO public")
            context.run_migrations()
    elif config.attributes.get("connection") is not None:
        connection = config.attributes["connection"]
        if not connection.in_transaction():
            raise MigrationSafetyError("A supplied test connection must own an explicit transaction.")
        run_on_connection(connection, settings)
    else:
        database = Database(settings)
        try:
            with database.connection() as connection:
                with connection.begin() as transaction:
                    run_on_connection(connection, settings)
                    if operation != "upgrade":
                        transaction.rollback()
        finally:
            database.close()
except (MigrationSafetyError, ValidationError) as error:
    message = str(error) if isinstance(error, MigrationSafetyError) else "Invalid migration settings; values withheld."
    raise CommandError(message) from None
except SQLAlchemyError as error:
    raise CommandError(f"Database migration failed ({type(error).__name__}); parameters and driver details withheld.") from None
