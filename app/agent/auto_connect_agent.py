import os
import sys
import asyncio
from dotenv import load_dotenv

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli
)
from livekit.plugins import silero, deepgram, cartesia, openai
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit import api, rtc
from app.utils.logger import setup_logger
from app.core.config import settings
import json

load_dotenv()
logger = setup_logger(__name__)

class VoiceAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="""You are a helpful, knowledgeable, and versatile AI assistant designed to provide accurate and thoughtful responses on a wide range of topics.
                CAPABILITIES:
                - Answer questions across diverse domains including technology, science, arts, history, current events, and everyday topics
                - Provide explanations, summaries, and analysis on complex subjects
                - Assist with creative tasks like writing, brainstorming, and problem-solving
                - Engage in natural, conversational dialogue while maintaining context

                GUIDELINES:
                - Be accurate, balanced, and objective in your responses
                - Acknowledge limitations when you don't have sufficient information
                - Provide nuanced perspectives on complex topics
                - Maintain a helpful, respectful, and friendly tone
                - Respect user privacy and avoid making assumptions
                - Keep responses concise and conversational for voice interaction""")

    async def on_enter(self):
        """Called when agent becomes active in a room"""
        logger.info("Voice assistant entered the room")
        await self.session.generate_reply(
            instructions="Greet the user warmly and let them know you're ready to help with voice interaction."
        )
    
    async def on_user_speech_committed(self, user_msg):
        """Called when user speech is recognized and committed"""
        try:
            if user_msg and user_msg.content:
                transcription_data = {
                    "type": "transcription", 
                    "text": user_msg.content
                }
                # Send transcription to all participants in the room
                await self.session.room.local_participant.publish_data(
                    json.dumps(transcription_data).encode('utf-8')
                )
                logger.info(f"Sent transcription to frontend: {user_msg.content}")
        except Exception as e:
            logger.error(f"Error sending transcription: {e}")
        
        # Continue with normal processing
        return await super().on_user_speech_committed(user_msg)

async def entrypoint(ctx: JobContext):
    """Agent entrypoint that connects to any room"""
    logger.info(f"Agent connecting to room: {ctx.room.name}")
    await ctx.connect()
    
    # Try to get agent config from room metadata
    agent_config = {}
    if ctx.room.metadata:
        try:
            import json
            agent_config = json.loads(ctx.room.metadata)
            logger.info(f"Using config from room metadata: {agent_config}")
        except json.JSONDecodeError:
            logger.warning("Failed to parse room metadata as JSON")
    
    # Get configuration with defaults
    model_id = agent_config.get("model_id", "gpt-4o-mini")
    voice_config = agent_config.get("voice", {})
    
    # Configure TTS
    tts = openai.TTS(
        model="tts-1",
        voice="alloy"  # Default voice
    )
    
    # Prewarm TTS
    try:
        tts.prewarm()
        logger.info("TTS prewarmed successfully")
    except Exception as e:
        logger.warning(f"TTS prewarm failed: {e}")
    
    session = AgentSession(
        stt=openai.STT(model="whisper-1", language=None),  # None for auto-detection
        llm=openai.LLM(model=model_id),
        tts=tts,
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=VoiceAssistant(),
    )

if __name__ == "__main__":
    # Configure worker to connect to any room
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))