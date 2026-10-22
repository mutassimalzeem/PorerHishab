from pydantic import BaseModel, Field


class FinanceQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=10)


class FinanceQuestionResponse(BaseModel):
    answer: str
    sources: list[dict]