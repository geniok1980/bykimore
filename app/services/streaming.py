import json
import traceback

from typing import AsyncGenerator

from fastapi.responses import StreamingResponse
from fastapi import HTTPException

from app.agent.chat_agent import AISupport
from app.models.user import User
from app.schemas.api import LegacyLLMRequest
from app.schemas.chat import ChatResponse
from app.utils.logger import setup_logger
from app.utils.openai_mapper import create_streaming_openai_chunk, serialize_ui_components

logger = setup_logger(__name__)


class StreamingService:
    _instance = None

    def __new__(cls, support_agent: AISupport):
        if cls._instance is None:
            cls._instance = super(StreamingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, support_agent: AISupport):
        if self._initialized:
            return
        self.support_agent = support_agent
        self._initialized = True

    async def streaming_chat(self, request: LegacyLLMRequest, current_user: User) -> StreamingResponse:
        try:
            async def generate_stream() -> AsyncGenerator[str, None]:
                response = await self.support_agent.ask(
                    question=request.user_message,
                    user_id=str(current_user.id),
                    chat_id=request.chat_id,
                    tenant_id=current_user.tenant_id
                )
                
                # Проверяем, есть ли структурированный ответ с UI компонентами
                if isinstance(response, dict) and "text_response" in response:
                    # Структурированный ответ с возможными UI компонентами
                    text_content = response.get("text_response", "")
                    ui_components = response.get("ui_components", [])
                    
                    # Сначала отправляем начальный чанк с ролью assistant
                    initial_chunk = await create_streaming_openai_chunk(role="assistant")
                    yield f"data: {json.dumps(initial_chunk)}\n\n"
                    
                    # Отправляем UI компоненты, если они есть
                    if ui_components:
                        serialized_components = serialize_ui_components(ui_components)
                        ui_chunk = await create_streaming_openai_chunk(
                            ui_components=serialized_components
                        )
                        yield f"data: {json.dumps(ui_chunk)}\n\n"
                    
                    # Затем стримим текстовый контент
                    if text_content:
                        chunk_size = 10
                        for i in range(0, len(text_content), chunk_size):
                            content_chunk = text_content[i:i+chunk_size]
                            text_chunk = await create_streaming_openai_chunk(
                                content=content_chunk
                            )
                            yield f"data: {json.dumps(text_chunk)}\n\n"
                    
                    # Финальный чанк
                    final_chunk = await create_streaming_openai_chunk(
                        finish_reason="stop"
                    )
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    
                elif "messages" in response and response["messages"]:
                    # Обычный текстовый ответ
                    full_content = response["messages"][0]
                    
                    # Отправляем начальный чанк с ролью assistant
                    initial_chunk = await create_streaming_openai_chunk(role="assistant")
                    yield f"data: {json.dumps(initial_chunk)}\n\n"
                    
                    chunk_size = 10
                    for i in range(0, len(full_content), chunk_size):
                        content_chunk = full_content[i:i+chunk_size]
                        text_chunk = await create_streaming_openai_chunk(
                            content=content_chunk
                        )
                        yield f"data: {json.dumps(text_chunk)}\n\n"
                    
                    # Финальный чанк
                    final_chunk = await create_streaming_openai_chunk(
                        finish_reason="stop"
                    )
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                
                else:
                    # Fallback для неожиданного формата ответа
                    logger.warning(f"Unexpected response format: {response}")
                    
                    # Отправляем начальный чанк с ролью assistant
                    initial_chunk = await create_streaming_openai_chunk(role="assistant")
                    yield f"data: {json.dumps(initial_chunk)}\n\n"
                    
                    # Отправляем сообщение об ошибке
                    error_message = "Извините, произошла ошибка при обработке запроса."
                    error_chunk = await create_streaming_openai_chunk(content=error_message)
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    
                    # Финальный чанк
                    final_chunk = await create_streaming_openai_chunk(finish_reason="stop")
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        except Exception as e:
            logger.error(f"Error in chat_completions: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))
