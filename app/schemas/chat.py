from typing import List, Optional, Dict, Any

from pydantic import BaseModel


class UIComponent(BaseModel):
    """UI component for generative UI responses"""
    type: str  # "weather_card", "chart", "table", "data_card", etc.
    data: Dict[str, Any]
    props: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Structured response with text and UI components"""
    text_response: str
    ui_components: Optional[List[UIComponent]] = None
    usage_data: Optional[Dict[str, Any]] = None  # для Lago billing


class ChatMessage(BaseModel):
    """Chat message model for API responses"""
    id: str
    user_message: str
    assistant_message: str
    timestamp: str
    chat_id: str
    user_id: str
    ui_components: Optional[List[UIComponent]] = None


class ChatHistoryResponse(BaseModel):
    """Response model for chat history endpoints"""
    messages: List[ChatMessage]
    total: int


class StreamingChatChunk(BaseModel):
    """Streaming chat response chunk"""
    type: str  # "text", "ui", "usage"
    content: Optional[str] = None
    component: Optional[UIComponent] = None
    usage: Optional[Dict[str, Any]] = None