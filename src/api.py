"""
Prima Form Extractor — REST API

Single endpoint: POST /extract
Receives a conversation array and returns structured form data.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from src.extractor import extract

app = FastAPI(
    title="Prima Form Extractor",
    description="Extract structured car insurance form data from unstructured Spanish conversations.",
    version="0.1.0",
)


class Message(BaseModel):
    role: str  # "user" | "assistant"
    text: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError('role must be "user" or "assistant"')
        return v


class ExtractRequest(BaseModel):
    messages: list[Message]

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[Message]) -> list[Message]:
        if not v:
            raise ValueError("messages must not be empty")
        return v


class ExtractResponse(BaseModel):
    extracted: dict
    missing: list[str]


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(body: ExtractRequest) -> ExtractResponse:
    """
    Extract structured Prima Seguros form fields from a Spanish conversation.

    - **messages**: array of conversation turns with `role` ("user"/"assistant") and `text`
    - Returns **extracted** (all fields, null if not found) and **missing** (required fields not found)
    """
    messages = [{"role": m.role, "text": m.text} for m in body.messages]
    try:
        result = extract(messages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ExtractResponse(**result)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
