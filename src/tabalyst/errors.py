# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public exceptions raised by Tabalyst."""


class TabalystError(Exception):
    """Base class for expected Tabalyst failures."""


class InputError(TabalystError, ValueError):
    """The CSV input or requested report path is invalid."""


class ConfigurationError(TabalystError, ValueError):
    """A configuration file or explicit configuration value is invalid."""


class ReportError(TabalystError):
    """Tabalyst could not write or render the requested report."""
