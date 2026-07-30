from app.common.enums import Environment


def is_production(environment: Environment) -> bool:
    """Return whether strict production behavior is required."""
    return environment is Environment.PRODUCTION


def is_local_environment(environment: Environment) -> bool:
    """Return whether developer-friendly behavior is appropriate."""
    return environment in {Environment.DEVELOPMENT, Environment.TEST}
