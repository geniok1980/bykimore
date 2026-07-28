from typing import Annotated
import json
import httpx
import aiohttp

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.user import User as DBUser
from app.schemas.token import LivekitToken
from app.utils.logger import setup_logger
from app.services.livekit_service import livekit_service
from livekit.api.agent_dispatch_service import AgentDispatchService, CreateAgentDispatchRequest
from livekit import api
from app.core.config import settings

logger = setup_logger(__name__)

router = APIRouter()

@router.post("/test_token", response_model=LivekitToken)
async def test_generate_token() -> LivekitToken:
    """Test endpoint without authentication for testing LiveKit integration"""
    print("🧪 === TEST TOKEN ENDPOINT CALLED ===")
    
    try:
        # Create room with test config
        room_name = "test-room"
        agent_config = {
            "model_id": "gpt-4o-mini",
            "language": "ru",
            "voice_id": "default"
        }
        
        print(f"🧪 Creating room: {room_name}")
        room = await livekit_service.create_room(room_name, json.dumps(agent_config))
        if room and hasattr(room, 'name'):
            print(f"🧪 Room created: {room.name}")
        else:
            print(f"🧪 Room exists or created (no details returned)")
        
        # Generate token
        print(f"🧪 Generating token for participant: test-user")
        token = livekit_service.generate_token(room_name, "test-user")
        print(f"🧪 Token generated successfully")
        
        return LivekitToken(
            token=token,
            room_name=room_name,
            participant_name="test-user"
        )
        
    except Exception as e:
        logger.error(f"Failed to generate test token: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate test token: {str(e)}")

@router.post("/generate_token", response_model=LivekitToken)
async def generate_token(
    current_user: Annotated[DBUser, Depends(get_current_user)]
) -> LivekitToken:
    print("🎫 === GENERATE TOKEN ENDPOINT CALLED ===")
    print(f"🎫 User: {current_user.username if current_user else 'None'}")
    print(f"🎫 User ID: {current_user.id if current_user else 'None'}")
    
    logger.info(f"Received generate livekit token request from user {current_user}")

    try:
        room_name = current_user.username
        participant_id = f"user_{current_user.username}"
        
        # Create room first
        agent_config = {
            "model_id": "gpt-4o-mini",
            "voice": {
                "language": "ru-RU",
                "voice_id": "default"
            }
        }
        
        await livekit_service.create_room(room_name, json.dumps(agent_config))
        
        # Generate token
        token = livekit_service.generate_token(room_name, participant_id)

        print(f"🎫 Token generated successfully for room: {room_name}")
        print(f"🎫 Token length: {len(token)}")
        print("🎫 === END GENERATE TOKEN ===")

        return LivekitToken(token=token, room_name=room_name)
    
    except Exception as e:
        logger.error(f"Failed to generate token: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")


@router.post("/dispatch_agent")
async def dispatch_agent(
    request_data: dict,
    current_user: Annotated[DBUser, Depends(get_current_user)]
):
    """Dispatch an agent to the user's room"""
    print("🤖 === DISPATCH AGENT ENDPOINT CALLED ===")
    print(f"🤖 User: {current_user.username if current_user else 'None'}")
    print(f"🤖 User ID: {current_user.id if current_user else 'None'}")
    print(f"🤖 Request data: {request_data}")
    
    logger.info(f"Dispatching agent to room for user {current_user.username}")
    
    try:
        room_name = request_data.get("room_name", current_user.username)
        print(f"🤖 Room name: {room_name}")
        
        # Create aiohttp session for the agent dispatch service
        async with aiohttp.ClientSession() as session:
            # Create LiveKit agent dispatch service client
            agent_service = AgentDispatchService(
                session=session,
                url=settings.LIVEKIT_URL,
                api_key=settings.LIVEKIT_API_KEY,
                api_secret=settings.LIVEKIT_API_SECRET
            )
            
            # Create agent dispatch request
            agent_dispatch = CreateAgentDispatchRequest()
            agent_dispatch.room = room_name
            agent_dispatch.agent_name = "voice-assistant"
            
            # Dispatch the agent
            dispatch_result = await agent_service.create_dispatch(agent_dispatch)
            
            logger.info(f"Agent dispatched successfully to room {room_name}: {dispatch_result}")
            
            print(f"🤖 Agent dispatched successfully to room: {room_name}")
            print(f"🤖 Dispatch ID: {dispatch_result.id if hasattr(dispatch_result, 'id') else 'None'}")
            print("🤖 === END DISPATCH AGENT ===")
            
            return {
                "status": "success", 
                "message": f"Agent dispatched to room {room_name}",
                "room_name": room_name,
                "dispatch_id": dispatch_result.id if hasattr(dispatch_result, 'id') else None
            }
        
    except Exception as e:
        logger.error(f"Failed to dispatch agent: {e}")
        print(f"🤖 ❌ Failed to dispatch agent: {e}")
        print("🤖 === END DISPATCH AGENT (ERROR) ===")
        raise HTTPException(status_code=500, detail=f"Failed to dispatch agent: {str(e)}")