from typing import Annotated
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_streaming_service, get_current_user
from app.models.user import User as DBUser
from app.schemas.api import LLMRequest, LegacyLLMRequest
from app.services.streaming import StreamingService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()

@router.post("/test")
async def test_endpoint():
    """Test endpoint without authentication"""
    logger.info("=== TEST ENDPOINT CALLED ===")
    return {"status": "success", "message": "Backend is reachable"}

@router.post("/completions")
async def chat_completions(
    request: LLMRequest,
    current_user: Annotated[DBUser, Depends(get_current_user)],
    streaming_service: StreamingService = Depends(get_streaming_service)
) -> StreamingResponse:
    logger.info("=== CHAT COMPLETIONS ENDPOINT CALLED ===")
    logger.info(f"Request received: {request}")
    logger.info(f"Current user: {current_user.username if current_user else 'None'}")
    logger.info(f"Messages count: {len(request.messages) if request.messages else 0}")
    
    try:
        # Extract the last user message from the messages array
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        logger.info(f"User messages found: {len(user_messages)}")
        
        if not user_messages:
            logger.error("No user message found in the request")
            raise ValueError("No user message found in the request")
        
        last_user_message = user_messages[-1].content
        logger.info(f"Last user message: {last_user_message}")
        
        # Create a legacy request for the streaming service
        chat_id = str(uuid.uuid4())
        legacy_request = LegacyLLMRequest(
            user_message=last_user_message,
            chat_id=chat_id
        )
        logger.info(f"Created legacy request with chat_id: {chat_id}")
        
        logger.info("Calling streaming service...")
        response = await streaming_service.streaming_chat(legacy_request, current_user)
        logger.info("Streaming service call completed successfully")
        
        return response
        
    except Exception as e:
        logger.error(f"Error in chat_completions: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        raise



