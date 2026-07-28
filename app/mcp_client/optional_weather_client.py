"""
Optional Weather MCP Client
Provides weather functionality with graceful fallback when MCP server is not available
"""
import asyncio
import logging
import json
import os
import sys
from typing import Dict, Any, Optional, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class OptionalWeatherMCPClient:
    """
    Optional Weather MCP Client that gracefully handles server unavailability
    """
    
    def __init__(self, server_path: Optional[str] = None, timeout: int = 30, enable_fallback: bool = True):
        """
        Initialize Optional Weather MCP Client
        
        Args:
            server_path: Path to weather server script
            timeout: Request timeout in seconds
            enable_fallback: Whether to enable fallback mode when server is unavailable
        """
        self.server_path = server_path or self._get_default_server_path()
        self.timeout = timeout
        self.enable_fallback = enable_fallback
        self.session: Optional[ClientSession] = None
        self.tools: Dict[str, Any] = {}
        self.is_connected = False
        self._connection_attempted = False
        
    def _get_default_server_path(self) -> str:
        """Get default path to weather server"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, "..", "mcp_server", "weather_server.py")
    
    async def connect(self) -> bool:
        """
        Connect to Weather MCP Server
        
        Returns:
            True if connection successful, False otherwise
        """
        if self._connection_attempted:
            return self.is_connected
            
        self._connection_attempted = True
        
        if not self.enable_fallback:
            # If fallback is disabled, raise exceptions normally
            return await self._connect_strict()
        
        try:
            return await self._connect_strict()
        except Exception as e:
            logger.warning(f"Weather MCP Server connection failed: {e}")
            logger.info("Continuing without Weather MCP Server - fallback mode enabled")
            self.is_connected = False
            return False
    
    async def _connect_strict(self) -> bool:
        """Connect to Weather MCP Server with strict error handling"""
        try:
            # Start the server process
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[self.server_path],
                env=None
            )
            
            # Create stdio client
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    self.session = session
                    
                    # Initialize the session
                    await session.initialize()
                    
                    # Load available tools
                    await self._load_tools()
                    
                    self.is_connected = True
                    logger.info("Successfully connected to Weather MCP Server")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to connect to Weather MCP Server: {e}")
            self.is_connected = False
            raise
    
    async def _load_tools(self):
        """Load available tools from the server"""
        try:
            if self.session:
                tools_response = await self.session.list_tools()
                self.tools = {
                    tool.name: {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema
                    }
                    for tool in tools_response.tools
                }
                logger.info(f"Loaded {len(self.tools)} tools from Weather MCP Server")
        except Exception as e:
            logger.error(f"Failed to load tools: {e}")
            if not self.enable_fallback:
                raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the server with fallback support
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            Tool response or fallback response
        """
        if not self.is_connected:
            if self.enable_fallback:
                return self._get_fallback_response(tool_name, arguments)
            else:
                raise RuntimeError("Weather MCP Server not connected and fallback is disabled")
        
        try:
            if not self.session:
                raise RuntimeError("No active session")
            
            # Call the tool with timeout
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments),
                timeout=self.timeout
            )
            
            if result.content:
                # Parse the response
                if len(result.content) > 0:
                    content = result.content[0]
                    if hasattr(content, 'text'):
                        try:
                            return json.loads(content.text)
                        except json.JSONDecodeError:
                            return {"result": content.text}
                    else:
                        return {"result": str(content)}
            
            return {"result": "No content returned"}
            
        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            if self.enable_fallback:
                logger.info(f"Using fallback response for tool '{tool_name}'")
                return self._get_fallback_response(tool_name, arguments)
            else:
                raise
    
    def _get_fallback_response(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get fallback response when MCP server is not available
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            Fallback response
        """
        if tool_name == "get_current_weather":
            city = arguments.get("city", "Unknown")
            return {
                "error": "Weather service temporarily unavailable",
                "message": f"Unable to get current weather for {city}. Weather MCP server is not connected.",
                "fallback": True,
                "city": city
            }
        elif tool_name == "get_weather_forecast":
            city = arguments.get("city", "Unknown")
            days = arguments.get("days", 5)
            return {
                "error": "Weather service temporarily unavailable", 
                "message": f"Unable to get {days}-day forecast for {city}. Weather MCP server is not connected.",
                "fallback": True,
                "city": city,
                "days": days
            }
        elif tool_name == "get_weather_by_coordinates":
            lat = arguments.get("lat", "Unknown")
            lon = arguments.get("lon", "Unknown")
            return {
                "error": "Weather service temporarily unavailable",
                "message": f"Unable to get weather for coordinates ({lat}, {lon}). Weather MCP server is not connected.",
                "fallback": True,
                "coordinates": {"lat": lat, "lon": lon}
            }
        elif tool_name == "health_check":
            return {
                "status": "disconnected",
                "message": "Weather MCP server is not connected",
                "fallback": True
            }
        else:
            return {
                "error": "Service temporarily unavailable",
                "message": f"Tool '{tool_name}' is not available. Weather MCP server is not connected.",
                "fallback": True,
                "tool": tool_name
            }
    
    async def get_current_weather(self, city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
        """Get current weather for a city"""
        arguments = {
            "city": city,
            "units": units
        }
        if country_code:
            arguments["country_code"] = country_code
            
        return await self.call_tool("get_current_weather", arguments)
    
    async def get_weather_by_coordinates(self, lat: float, lon: float, units: str = "metric") -> Dict[str, Any]:
        """Get current weather by coordinates"""
        arguments = {
            "lat": lat,
            "lon": lon,
            "units": units
        }
        return await self.call_tool("get_weather_by_coordinates", arguments)
    
    async def get_weather_forecast(self, city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
        """Get weather forecast for a city"""
        arguments = {
            "city": city,
            "days": days,
            "units": units
        }
        if country_code:
            arguments["country_code"] = country_code
            
        return await self.call_tool("get_weather_forecast", arguments)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check server health"""
        return await self.call_tool("health_check", {})
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tools"""
        if self.is_connected:
            return list(self.tools.keys())
        else:
            return []
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool"""
        if self.is_connected:
            return self.tools.get(tool_name)
        else:
            return None
    
    async def disconnect(self):
        """Disconnect from the server"""
        if self.session:
            try:
                # Note: stdio client handles cleanup automatically
                self.session = None
                self.is_connected = False
                logger.info("Disconnected from Weather MCP Server")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")


# Global client instance
_weather_client: Optional[OptionalWeatherMCPClient] = None


async def get_weather_client(enable_fallback: bool = True) -> OptionalWeatherMCPClient:
    """
    Get global weather client instance
    
    Args:
        enable_fallback: Whether to enable fallback mode
        
    Returns:
        Weather client instance
    """
    global _weather_client
    if _weather_client is None:
        _weather_client = OptionalWeatherMCPClient(enable_fallback=enable_fallback)
        await _weather_client.connect()
    return _weather_client


async def get_weather(city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
    """
    Get current weather for a city
    
    Args:
        city: City name
        country_code: Optional country code
        units: Temperature units (metric, imperial, kelvin)
        
    Returns:
        Weather data or fallback response
    """
    client = await get_weather_client()
    return await client.get_current_weather(city, country_code, units)


async def get_forecast(city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
    """
    Get weather forecast for a city
    
    Args:
        city: City name
        country_code: Optional country code
        days: Number of forecast days
        units: Temperature units (metric, imperial, kelvin)
        
    Returns:
        Forecast data or fallback response
    """
    client = await get_weather_client()
    return await client.get_weather_forecast(city, country_code, days, units)


async def test_client():
    """Test the optional weather client"""
    print("Testing Optional Weather MCP Client...")
    
    client = OptionalWeatherMCPClient(enable_fallback=True)
    
    # Test connection
    connected = await client.connect()
    print(f"Connection status: {'Connected' if connected else 'Fallback mode'}")
    
    if connected:
        print(f"Available tools: {client.get_available_tools()}")
    
    # Test weather calls (should work in both connected and fallback modes)
    try:
        print("\nTesting current weather...")
        weather = await client.get_current_weather("London", "GB")
        print(f"Weather result: {weather}")
        
        print("\nTesting forecast...")
        forecast = await client.get_weather_forecast("London", "GB", 3)
        print(f"Forecast result: {forecast}")
        
        print("\nTesting health check...")
        health = await client.health_check()
        print(f"Health check: {health}")
        
    except Exception as e:
        print(f"Error during testing: {e}")
    
    finally:
        await client.disconnect()
        print("Client disconnected")


if __name__ == "__main__":
    asyncio.run(test_client())