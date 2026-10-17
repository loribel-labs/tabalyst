# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Base class of the serializable models of the Report document."""

from pydantic import BaseModel, ConfigDict


class ResultModel(BaseModel):
    """A model that refuses members it does not declare."""

    model_config = ConfigDict(extra="forbid")
