from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class LLMRequest(BaseModel):
    messages: List[ChatMessage] = Field(description="Chat messages in OpenAI format")
    model: Optional[str] = Field(default="gpt-3.5-turbo", description="Model name")
    stream: Optional[bool] = Field(default=True, description="Whether to stream the response")
    temperature: Optional[float] = Field(default=0.7, description="Temperature for response generation")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens in response")

# Legacy format for backward compatibility
class LegacyLLMRequest(BaseModel):
    user_message: str = Field(description="Chat message")
    chat_id: str = Field(description="Chat ID")

