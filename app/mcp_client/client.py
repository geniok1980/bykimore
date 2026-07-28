from contextlib import AsyncExitStack
from typing import List, Any, Tuple
import asyncio

from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools

from app.utils.logger import setup_logger
from app.mcp_client.optional_client import OptionalMCPClient, get_optional_mcp_client

logger = setup_logger(__name__)


class MCPClientWrapper:
    def __init__(self, server_url: str, name: str):
        self.server_url = server_url
        self.name = name
        self.session = None
        self.tools = []
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        
    async def connect(self) -> None:
        logger.info(f"Client {self.name} connecting to MCP server at {self.server_url}")
        
        try:
            (read, write) = await self.exit_stack.enter_async_context(sse_client(f"{self.server_url}"))
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))

            self.session = session
            await self.session.initialize()
            logger.info("MCP session initialized successfully")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {str(e)}")
            raise
    
    async def load_tools(self) -> List[Any]:
        try:
            logger.info("Loading MCP tools...")
            self.tools = await load_mcp_tools(self.session)
            tool_names = [tool.name for tool in self.tools]
            logger.info(f"Loaded {len(self.tools)} tools: {tool_names}")
            return self.tools
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Failed to load tools: {str(e)}\n{error_details}")
            return []
    
    async def close(self) -> None:
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
            except Exception as e:
                logger.info("Error during cleanup: %s", str(e))

async def get_mcp_client(server_url: str, name: str, enable_fallback: bool = True) -> Tuple[MCPClientWrapper | None, List[Any]]:
    """
    Get MCP client with optional fallback support
    
    Args:
        server_url: URL of the MCP server
        name: Name of the client
        enable_fallback: Whether to enable fallback mode (default: True)
        
    Returns:
        Tuple of (client, tools) - client may be None if connection failed and fallback is disabled
    """
    if enable_fallback:
        # Use optional client with graceful fallback
        try:
            optional_client, tools = await get_optional_mcp_client(server_url, name, enable_fallback=True)
            # Wrap the optional client in the original wrapper interface
            if optional_client.is_connected:
                # Create a wrapper that delegates to the optional client
                wrapper = MCPClientWrapper(server_url, name)
                wrapper.session = optional_client.session
                wrapper.tools = tools
                return wrapper, tools
            else:
                # Return None for client but keep the optional client for potential future use
                logger.info(f"MCP client '{name}' not connected - returning None with fallback enabled")
                return None, []
        except Exception as e:
            logger.error(f"MCP '{name}' connection failed for {server_url}: {str(e)}")
            return None, []
    else:
        # Use original strict behavior
        client = MCPClientWrapper(server_url, name)
        try:
            await client.connect()
            tools = await client.load_tools()
            return client, tools
        except Exception as e:
            logger.error(f"MCP '{name}' connection failed for {server_url}: {str(e)}")
            raise