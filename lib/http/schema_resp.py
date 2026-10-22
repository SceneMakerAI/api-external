from pydantic import BaseModel


class Resp_Base(BaseModel):
    code: int
    result: str | None = None
