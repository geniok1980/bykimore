import time
import uuid

from typing import Dict, Any, Optional, List


async def create_streaming_openai_chunk(
        content: Optional[str] = None,
        role: Optional[str] = None,
        finish_reason: Optional[str] = None,
        ui_components: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason
            }
        ]
    }

    if content:
        chunk["choices"][0]["delta"]["content"] = content

    if role:
        chunk["choices"][0]["delta"]["role"] = role
    
    if ui_components:
        chunk["choices"][0]["delta"]["ui_components"] = ui_components

    return chunk


def serialize_ui_components(ui_components):
    """Сериализует UI компоненты для JSON"""
    if not ui_components:
        return []
    
    def serialize_object(obj):
        """Рекурсивно сериализует объект"""
        if obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, list):
            return [serialize_object(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: serialize_object(value) for key, value in obj.items()}
        elif hasattr(obj, 'model_dump'):
            # Pydantic модель
            return obj.model_dump()
        elif hasattr(obj, '__dict__'):
            # Объект с атрибутами
            return {key: serialize_object(value) for key, value in obj.__dict__.items()}
        else:
            # Для всех остальных типов
            return str(obj)
    
    serialized = []
    for component in ui_components:
        try:
            serialized_component = serialize_object(component)
            serialized.append(serialized_component)
        except Exception as e:
            # В случае ошибки добавляем строковое представление
            serialized.append(str(component))
    
    return serialized