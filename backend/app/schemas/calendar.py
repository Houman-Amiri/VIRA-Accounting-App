"""Global calendar policy; date-only storage remains Gregorian ISO."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class CalendarUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calendar: Literal["jalali", "gregorian"]
    version_id: Annotated[StrictInt, Field(ge=0)]


class CalendarRead(CalendarUpdate):
    timezone: Literal["Asia/Tehran"] = "Asia/Tehran"
    scope: Literal["installation"] = "installation"
