"""
Optional MCP Client Wrapper
Provides graceful fallback when MCP servers are not available
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class OptionalMCPClient:
    """
    Optional MCP Client that gracefully handles connection failures
    """
    
    def __init__(self, server_url: str, name: str, enable_fallback: bool = True):
        self.server_url = server_url
        self.name = name
        self.enable_fallback = enable_fallback
        self.session = None
        self.tools = []
        self.is_connected = False
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        
    async def connect(self) -> bool:
        """
        Attempt to connect to MCP server
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self.enable_fallback:
            # If fallback is disabled, raise exceptions normally
            return await self._connect_strict()
        
        try:
            return await self._connect_strict()
        except Exception as e:
            logger.warning(f"MCP client '{self.name}' failed to connect to {self.server_url}: {str(e)}")
            logger.info(f"Continuing without MCP client '{self.name}' - fallback mode enabled")
            self.is_connected = False
            return False
    
    async def _connect_strict(self) -> bool:
        """Connect to MCP server with strict error handling"""
        logger.info(f"Client {self.name} connecting to MCP server at {self.server_url}")
        
        try:
            (read, write) = await self.exit_stack.enter_async_context(sse_client(f"{self.server_url}"))
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))

            self.session = session
            await self.session.initialize()
            self.is_connected = True
            logger.info(f"MCP client '{self.name}' connected successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to connect MCP client '{self.name}' to server: {str(e)}")
            self.is_connected = False
            raise
    
    async def load_tools(self) -> List[Any]:
        """
        Load tools from MCP server
        
        Returns:
            List of tools if connected, empty list otherwise
        """
        if not self.is_connected or not self.session:
            logger.debug(f"MCP client '{self.name}' not connected - returning empty tools list")
            return []
        
        try:
            logger.info(f"Loading MCP tools for client '{self.name}'...")
            self.tools = await load_mcp_tools(self.session)
            tool_names = [tool.name for tool in self.tools]
            logger.info(f"Loaded {len(self.tools)} tools for '{self.name}': {tool_names}")
            return self.tools
        except Exception as e:
            logger.error(f"Failed to load tools for '{self.name}': {str(e)}")
            if self.enable_fallback:
                logger.info(f"Continuing without tools for '{self.name}' - fallback mode enabled")
                return []
            else:
                raise
    
    async def close(self) -> None:
        """Close MCP client connection"""
        async with self._cleanup_lock:
            try:
                if self.exit_stack:
                    await self.exit_stack.aclose()
                self.session = None
                self.is_connected = False
                logger.debug(f"MCP client '{self.name}' closed successfully")
            except Exception as e:
                logger.warning(f"Error during cleanup of '{self.name}': {str(e)}")


async def get_optional_mcp_client(server_url: str, name: str, enable_fallback: bool = True) -> Tuple[OptionalMCPClient, List[Any]]:
    """
    Get optional MCP client with graceful fallback
    
    Args:
        server_url: URL of the MCP server
        name: Name of the client
        enable_fallback: Whether to enable fallback mode (default: True)
        
    Returns:
        Tuple of (client, tools) - tools will be empty if connection failed and fallback is enabled
    """
    client = OptionalMCPClient(server_url, name, enable_fallback)
    
    # Attempt to connect
    connected = await client.connect()
    
    if connected:
        # Load tools if connected
        tools = await client.load_tools()
        return client, tools
    else:
        # Return client with empty tools if fallback is enabled
        if enable_fallback:
            return client, []
        else:
            # Re-raise the connection error if fallback is disabled
            raise RuntimeError(f"Failed to connect to MCP server '{name}' at {server_url}")


class OptionalMCPTools:
    """
    Optional MCP Tools manager that gracefully handles missing connections
    """
    
    def __init__(self, mcp_configs: List[Dict[str, Any]], enable_fallback: bool = True):
        self.mcp_configs = mcp_configs or []
        self.enable_fallback = enable_fallback
        self.tools = []
        self.mcp_clients = []
        self.connected_clients = []
        
    async def setup_mcp_tools(self) -> List[Any]:
        """
        Setup MCP tools with optional fallback
        
        Returns:
            List of successfully loaded tools
        """
        all_tools = []
        
        for config in self.mcp_configs:
            client_name = config.get("client_name")
            server_url = config.get("server_url")
            
            if not server_url:
                logger.warning(f"No server URL provided for MCP client '{client_name}' - skipping")
                continue
            
            try:
                client, tools = await get_optional_mcp_client(
                    server_url, 
                    client_name, 
                    self.enable_fallback
                )
                
                self.mcp_clients.append(client)
                
                if client.is_connected:
                    self.connected_clients.append(client)
                    all_tools.extend(tools)
                    logger.info(f"MCP client '{client_name}' added {len(tools)} tools")
                else:
                    logger.info(f"MCP client '{client_name}' not connected - no tools added")
                    
            except Exception as e:
                if self.enable_fallback:
                    logger.warning(f"Failed to setup MCP client '{client_name}': {str(e)} - continuing without it")
                else:
                    logger.error(f"Failed to setup MCP client '{client_name}': {str(e)}")
                    raise
        
        self.tools = all_tools
        logger.info(f"Total MCP tools loaded: {len(all_tools)} from {len(self.connected_clients)} connected clients")
        return all_tools
    
    async def cleanup(self) -> None:
        """Clean up all MCP client connections"""
        for client in self.mcp_clients:
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing MCP client '{client.name}': {str(e)}")
        
        self.mcp_clients.clear()
        self.connected_clients.clear()
        self.tools.clear()
        logger.info("All MCP clients cleaned up")
    
    def get_connected_client_names(self) -> List[str]:
        """Get names of successfully connected clients"""
        return [client.name for client in self.connected_clients]
    
    def get_total_tools_count(self) -> int:
        """Get total number of loaded tools"""
        return len(self.tools)
    
    def is_any_client_connected(self) -> bool:
        """Check if any MCP client is connected"""
        return len(self.connected_clients) > 0