from typing import Literal

from pydantic import BaseModel, ConfigDict


class LivenessResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ready"}]})

    status: Literal["ready"]
