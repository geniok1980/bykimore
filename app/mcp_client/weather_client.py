"""
Weather MCP Client using FastMCP 2.0
Provides interface to interact with Weather MCP Server
"""
import asyncio
import logging
import json
from typing import Dict, Any, Optional, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import subprocess
import sys
import os

logger = logging.getLogger(__name__)


class WeatherMCPClient:
    """Client for Weather MCP Server using FastMCP 2.0"""
    
    def __init__(self, server_path: Optional[str] = None, timeout: int = 30):
        """
        Initialize Weather MCP Client
        
        Args:
            server_path: Path to weather server script
            timeout: Request timeout in seconds
        """
        self.server_path = server_path or self._get_default_server_path()
        self.timeout = timeout
        self.session: Optional[ClientSession] = None
        self.tools: Dict[str, Any] = {}
        
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
                    
                    logger.info("Successfully connected to Weather MCP Server")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to connect to Weather MCP Server: {e}")
            return False
    
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
                logger.info(f"Loaded {len(self.tools)} tools from server")
        except Exception as e:
            logger.error(f"Failed to load tools: {e}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the server
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            Tool response
        """
        try:
            if not self.session:
                return {"error": "Not connected to server"}
            
            if tool_name not in self.tools:
                return {"error": f"Tool '{tool_name}' not available"}
            
            # Call the tool with timeout
            response = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments),
                timeout=self.timeout
            )
            
            if response.isError:
                return {"error": f"Tool error: {response.content}"}
            
            # Parse the response content
            if hasattr(response, 'content') and response.content:
                if isinstance(response.content, list) and len(response.content) > 0:
                    content = response.content[0]
                    if hasattr(content, 'text'):
                        try:
                            return json.loads(content.text)
                        except json.JSONDecodeError:
                            return {"result": content.text}
                    else:
                        return {"result": str(content)}
                else:
                    return {"result": str(response.content)}
            
            return {"result": "No content returned"}
            
        except asyncio.TimeoutError:
            return {"error": f"Tool call timed out after {self.timeout} seconds"}
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {"error": str(e)}
    
    async def get_current_weather(self, city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
        """
        Get current weather for a city
        
        Args:
            city: City name
            country_code: Country code (optional)
            units: Units (metric, imperial, kelvin)
            
        Returns:
            Weather data
        """
        arguments = {
            "city": city,
            "units": units
        }
        if country_code:
            arguments["country_code"] = country_code
            
        return await self.call_tool("get_current_weather", arguments)
    
    async def get_weather_by_coordinates(self, lat: float, lon: float, units: str = "metric") -> Dict[str, Any]:
        """
        Get weather by coordinates
        
        Args:
            lat: Latitude
            lon: Longitude
            units: Units (metric, imperial, kelvin)
            
        Returns:
            Weather data
        """
        arguments = {
            "lat": lat,
            "lon": lon,
            "units": units
        }
        return await self.call_tool("get_weather_by_coordinates", arguments)
    
    async def get_weather_forecast(self, city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
        """
        Get weather forecast
        
        Args:
            city: City name
            country_code: Country code (optional)
            days: Number of days (1-5)
            units: Units (metric, imperial, kelvin)
            
        Returns:
            Forecast data
        """
        arguments = {
            "city": city,
            "days": days,
            "units": units
        }
        if country_code:
            arguments["country_code"] = country_code
            
        return await self.call_tool("get_weather_forecast", arguments)
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check server health
        
        Returns:
            Health status
        """
        return await self.call_tool("health_check", {})
    
    def get_available_tools(self) -> List[str]:
        """
        Get list of available tools
        
        Returns:
            List of tool names
        """
        return list(self.tools.keys())
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific tool
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool information or None if not found
        """
        return self.tools.get(tool_name)
    
    async def disconnect(self):
        """Disconnect from the server"""
        if self.session:
            try:
                await self.session.close()
                self.session = None
                logger.info("Disconnected from Weather MCP Server")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")


# Global client instance
_weather_client: Optional[WeatherMCPClient] = None


async def get_weather_client() -> WeatherMCPClient:
    """Get or create global weather client instance"""
    global _weather_client
    if _weather_client is None:
        _weather_client = WeatherMCPClient()
        await _weather_client.connect()
    return _weather_client


async def get_weather(city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
    """
    Convenience function to get current weather
    
    Args:
        city: City name
        country_code: Country code (optional)
        units: Units (metric, imperial, kelvin)
        
    Returns:
        Weather data
    """
    client = await get_weather_client()
    return await client.get_current_weather(city, country_code, units)


async def get_forecast(city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
    """
    Convenience function to get weather forecast
    
    Args:
        city: City name
        country_code: Country code (optional)
        days: Number of days (1-5)
        units: Units (metric, imperial, kelvin)
        
    Returns:
        Forecast data
    """
    client = await get_weather_client()
    return await client.get_weather_forecast(city, country_code, days, units)


async def test_client():
    """Test the weather client"""
    try:
        print("🌤️ Testing Weather MCP Client...")
        
        client = WeatherMCPClient()
        connected = await client.connect()
        
        if not connected:
            print("❌ Failed to connect to server")
            return
        
        print("✅ Connected to server")
        
        # Test health check
        health = await client.health_check()
        print(f"Health check: {health}")
        
        # Test current weather
        weather = await client.get_current_weather("Moscow", "RU")
        print(f"Moscow weather: {weather}")
        
        # Test forecast
        forecast = await client.get_weather_forecast("London", "GB", 3)
        print(f"London forecast: {forecast}")
        
        await client.disconnect()
        print("✅ Test completed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_client())