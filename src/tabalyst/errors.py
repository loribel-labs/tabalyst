"""Public exceptions raised by Tabalyst."""


class TabalystError(Exception):
    """Base class for expected Tabalyst failures."""


class InputError(TabalystError, ValueError):
    """The CSV input or requested report path is invalid."""


class ConfigurationError(TabalystError, ValueError):
    """A configuration file or explicit configuration value is invalid."""


class ReportError(TabalystError):
    """Tabalyst could not write or render the requested report."""
