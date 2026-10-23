# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Failures of Dedup that carry the stable ``reason`` of a failed report."""

from collections.abc import Callable
from typing import Literal

from tabalyst.errors import InputError, ReportError

FailureReason = Literal[
    "row_limit_exceeded",
    "invalid_csv",
    "encoding_error",
    "source_unreadable",
    "source_changed",
    "insufficient_disk_space",
    "storage_unavailable",
    "output_unwritable",
    "unexpected_error",
]


class DedupInputError(InputError):
    """A source cannot be processed (design dedup 12.4: exit code 4).

    ``records_read`` is the number of records read when the failure happened and
    ``limit`` the exceeded limit, each ``None`` when it does not apply.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: FailureReason,
        records_read: int | None = None,
        limit: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason: FailureReason = reason
        self.records_read = records_read
        self.limit = limit

    def __reduce__(self) -> tuple[Callable[..., "DedupInputError"], tuple[object, ...]]:
        # The keyword-only `reason` is not in `args`, so the default would not unpickle.
        return _rebuild_input_error, (
            str(self), self.reason, self.records_read, self.limit,
        )


class DedupReportError(ReportError):
    """Storage or output problem, or an internal failure (design dedup 12.4: exit code 1)."""

    def __init__(
        self,
        message: str,
        *,
        reason: FailureReason,
        records_read: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason: FailureReason = reason
        self.records_read = records_read

    def __reduce__(self) -> tuple[Callable[..., "DedupReportError"], tuple[object, ...]]:
        return _rebuild_report_error, (str(self), self.reason, self.records_read)


def _rebuild_input_error(
    message: str, reason: FailureReason, records_read: int | None, limit: int | None
) -> DedupInputError:
    return DedupInputError(message, reason=reason, records_read=records_read, limit=limit)


def _rebuild_report_error(
    message: str, reason: FailureReason, records_read: int | None
) -> DedupReportError:
    return DedupReportError(message, reason=reason, records_read=records_read)
