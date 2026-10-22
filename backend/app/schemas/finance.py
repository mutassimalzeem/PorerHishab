from pydantic import BaseModel, Field


class FinanceQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class FinanceQueryResponse(BaseModel):
    answer: str
    intent: str
    sources: list[dict]