import argparse
import logging

from pydantic import BaseModel, Field

from .command import init, run
from .settings import AbstractSettings, InitSettings, RunSettings

log = logging.getLogger(__name__)


class _LoggingSettings(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class LoggingSettings(AbstractSettings):
    """Configuration for logging settings."""

    logging: _LoggingSettings = Field(default_factory=_LoggingSettings)


def main():
    """
    Entry point for the Outlook Absence Helper application.

    Configures logging, loads settings, and executes the appropriate command.
    """
    # Initial logging configuration..
    logging.basicConfig(level=logging.INFO)

    # Load logging settings. This only parses the relevant settings from the environment.
    logging_settings = LoggingSettings()

    # Adjust logging configuration, based on settings.
    logging.basicConfig(
        level=logging_settings.logging.level,
        format=logging_settings.logging.format,
        force=True,
    )

    # Tame http logging from Azure SDKs for log level INFO.
    if log.getEffectiveLevel() == logging.INFO:
        azure_logger = logging.getLogger(
            "azure.core.pipeline.policies.http_logging_policy"
        )
        azure_logger.setLevel(logging.WARN)

    # Set up command-line argument parsing.
    parser = argparse.ArgumentParser(
        description="Outlook absence helper for automatic auto-reply management"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Add 'init' command.
    init_parser = subparsers.add_parser("init", help="Initialize the application")
    init_parser.set_defaults(func=init, settings_cls=InitSettings)

    # Add 'run' command.
    run_parser = subparsers.add_parser("run", help="Run the application")
    run_parser.set_defaults(func=run, settings_cls=RunSettings)

    # Parse arguments.
    args = parser.parse_args()

    # Default to 'run' if no command provided.
    if args.command is None:
        args.command = "run"
        args.func = run
        args.settings_cls = RunSettings

    log.debug(f"Arguments: {args}")

    # Load settings for command.
    settings = args.settings_cls()

    log.debug(f"Settings: {settings.model_dump_json(indent=2)}")

    # Execute the selected command.
    args.func(settings)


if __name__ == "__main__":
    main()
