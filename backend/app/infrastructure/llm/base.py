from abc import ABC, abstractmethod
from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str  # system/user/assistant
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_input: int
    tokens_output: int
    latency_ms: int


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[LLMMessage],
        output_schema: dict,
        temperature: float = 0.1,
    ) -> dict: ...
