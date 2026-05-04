from .config import MigrationConfig, ProjectConfig, load_config

__all__ = [
    "ProjectConfig",
    "MigrationConfig",
    "IntentionMigrationEngine",
    "load_config",
]

__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "IntentionMigrationEngine":
        from .engine import IntentionMigrationEngine

        return IntentionMigrationEngine
    raise AttributeError(f"module 'itmweb' has no attribute {name!r}")
