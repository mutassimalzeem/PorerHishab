"""Password lengths count Unicode code points; values are never transformed.

New credentials require eight characters. Login accepts nonempty candidates for
compatibility, with the same maximum as creation and recovery.
"""
from typing import Annotated
from pydantic import StringConstraints

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024
NewPassword = Annotated[str, StringConstraints(
    min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH,
)]
LoginPassword = Annotated[str, StringConstraints(
    min_length=1, max_length=MAX_PASSWORD_LENGTH,
)]
