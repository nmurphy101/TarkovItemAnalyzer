import json
import logging
import logging.config
import logging.handlers
import os
from logging import LogRecord


class ImmediateFlushHandler(logging.StreamHandler):
    def emit(self, record: LogRecord) -> None:
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)


class ImmediateFlushRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def emit(self, record: LogRecord) -> None:
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)


if os.path.exists("_internal/settings.json"):
    with open("_internal/settings.json") as settings_file:
        settings = json.load(settings_file)
        debug_level = settings.get("debug_level", "INFO")

# Centralized logging configuration using dictConfig
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,  # Ensure existing loggers are not disabled
    "handlers": {  # Handlers define where and how logs are output
        "file": {
            "class": "logger_config.ImmediateFlushRotatingFileHandler",  # Custom handler class for writing logs to a file
            "filename": "debug.log",
            "maxBytes": 100000,              # Maximum size of a log file in bytes before rotation
            "backupCount": 3,                # Number of backup files to keep
            "formatter": "simple",           # Refer to the formatter defined below
            "errors": "replace",
        },
        "console": {
            "class": "logger_config.ImmediateFlushHandler",  # Custom handler class for writing logs to the console
            "formatter": "simple",                           # Refer to the formatter defined below
        },
    },
    "formatters": {
        "simple": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "root": {
        "level": debug_level,
        "handlers": ["file", "console"],
    },
})

logger = logging.getLogger()
