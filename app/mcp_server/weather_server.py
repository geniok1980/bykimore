"""
Weather MCP Server using FastMCP 2.0
Provides weather information tools using OpenWeatherMap API
"""
import requests
import logging
from typing import Optional, Dict, Any
from fastmcp import FastMCP
from weather_config import get_weather_config, validate_config, print_config_summary

# Load and validate configuration
config = get_weather_config()
is_valid, errors = validate_config()
if not is_valid:
    print("❌ Configuration errors:")
    for error in errors:
        print(f"  - {error}")
    exit(1)
print_config_summary()

# Setup logging
logging.basicConfig(level=getattr(logging, config.log_level))
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("Weather Server 🌤️")

# OpenWeatherMap API configuration
API_KEY = config.openweather_api_key
BASE_URL = config.openweather_base_url

logger.info("🌤️ Starting Weather MCP Server...")
logger.info(f"Server will be available at: http://{config.host}:{config.port}")
logger.info(f"Transport: {config.transport}")
logger.info(f"API Key configured: {'Yes' if API_KEY else 'No'}")
logger.info("Press Ctrl+C to stop the server")
logger.info("=" * 50)

if API_KEY:
    logger.info("✅ OpenWeatherMap API Key configured")
else:
    logger.error("❌ OpenWeatherMap API Key not configured")
    exit(1)


@mcp.tool()
def get_current_weather(city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
    """
    Получение текущей погоды по названию города
    
    Args:
        city: Название города
        country_code: Код страны (опционально, например 'US', 'RU')
        units: Единицы измерения (metric, imperial, kelvin)
    
    Returns:
        Данные о текущей погоде
    """
    try:
        if not API_KEY:
            return {"error": "OpenWeatherMap API key not configured"}
            
        # Prepare location string
        location = city
        if country_code:
            location = f"{city},{country_code}"
        
        # Make API request
        url = f"{BASE_URL}/weather"
        params = {
            "q": location,
            "appid": API_KEY,
            "units": units
        }
        
        response = requests.get(url, params=params, timeout=config.request_timeout)
        response.raise_for_status()
        
        data = response.json()
        
        # Format response
        result = {
            "location": {
                "city": data["name"],
                "country": data["sys"]["country"],
                "coordinates": {
                    "lat": data["coord"]["lat"],
                    "lon": data["coord"]["lon"]
                }
            },
            "weather": {
                "main": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
                "icon": data["weather"][0]["icon"],
                "temperature": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"]
            },
            "wind": {
                "speed": data["wind"]["speed"],
                "direction": data["wind"].get("deg", 0)
            },
            "units": units,
            "timestamp": data["dt"]
        }
        
        logger.info(f"Successfully retrieved weather for {city}")
        return result
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching weather data: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


@mcp.tool()
def get_weather_by_coordinates(lat: float, lon: float, units: str = "metric") -> Dict[str, Any]:
    """
    Получение погоды по координатам
    
    Args:
        lat: Широта (-90 до 90)
        lon: Долгота (-180 до 180)
        units: Единицы измерения (metric, imperial, kelvin)
    
    Returns:
        Данные о погоде по координатам
    """
    try:
        if not API_KEY:
            return {"error": "OpenWeatherMap API key not configured"}
            
        # Validate coordinates
        if not (-90 <= lat <= 90):
            return {"error": "Latitude must be between -90 and 90"}
        if not (-180 <= lon <= 180):
            return {"error": "Longitude must be between -180 and 180"}
        
        # Make API request
        url = f"{BASE_URL}/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": API_KEY,
            "units": units
        }
        
        response = requests.get(url, params=params, timeout=config.request_timeout)
        response.raise_for_status()
        
        data = response.json()
        
        # Format response
        result = {
            "location": {
                "city": data["name"],
                "country": data["sys"]["country"],
                "coordinates": {
                    "lat": data["coord"]["lat"],
                    "lon": data["coord"]["lon"]
                }
            },
            "weather": {
                "main": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
                "icon": data["weather"][0]["icon"],
                "temperature": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"]
            },
            "wind": {
                "speed": data["wind"]["speed"],
                "direction": data["wind"].get("deg", 0)
            },
            "units": units,
            "timestamp": data["dt"]
        }
        
        logger.info(f"Successfully retrieved weather for coordinates {lat}, {lon}")
        return result
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching weather data: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


@mcp.tool()
def get_weather_forecast(city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
    """
    Получение прогноза погоды
    
    Args:
        city: Название города
        country_code: Код страны (опционально)
        days: Количество дней прогноза (1-5)
        units: Единицы измерения (metric, imperial, kelvin)
    
    Returns:
        Прогноз погоды
    """
    try:
        if not API_KEY:
            return {"error": "OpenWeatherMap API key not configured"}
            
        # Validate days
        if not (1 <= days <= 5):
            return {"error": "Days must be between 1 and 5"}
        
        # Prepare location string
        location = city
        if country_code:
            location = f"{city},{country_code}"
        
        # Make API request
        url = f"{BASE_URL}/forecast"
        params = {
            "q": location,
            "appid": API_KEY,
            "units": units,
            "cnt": days * 8  # 8 forecasts per day (every 3 hours)
        }
        
        response = requests.get(url, params=params, timeout=config.request_timeout)
        response.raise_for_status()
        
        data = response.json()
        
        # Format response
        forecasts = []
        for item in data["list"]:
            forecast = {
                "datetime": item["dt"],
                "weather": {
                    "main": item["weather"][0]["main"],
                    "description": item["weather"][0]["description"],
                    "icon": item["weather"][0]["icon"],
                    "temperature": item["main"]["temp"],
                    "feels_like": item["main"]["feels_like"],
                    "humidity": item["main"]["humidity"],
                    "pressure": item["main"]["pressure"]
                },
                "wind": {
                    "speed": item["wind"]["speed"],
                    "direction": item["wind"].get("deg", 0)
                }
            }
            forecasts.append(forecast)
        
        result = {
            "location": {
                "city": data["city"]["name"],
                "country": data["city"]["country"],
                "coordinates": {
                    "lat": data["city"]["coord"]["lat"],
                    "lon": data["city"]["coord"]["lon"]
                }
            },
            "forecasts": forecasts,
            "units": units,
            "days_requested": days
        }
        
        logger.info(f"Successfully retrieved {days}-day forecast for {city}")
        return result
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching forecast data: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


@mcp.tool()
def health_check() -> Dict[str, Any]:
    """
    Проверка состояния сервера
    
    Returns:
        Статус сервера и конфигурации
    """
    try:
        if not API_KEY:
            return {
                "status": "unhealthy",
                "error": "API key not configured"
            }
            
        # Test API connectivity
        url = f"{BASE_URL}/weather"
        params = {
            "q": "London",
            "appid": API_KEY,
            "units": "metric"
        }
        
        response = requests.get(url, params=params, timeout=5)
        api_status = "healthy" if response.status_code == 200 else "unhealthy"
        
    except Exception:
        api_status = "unhealthy"
    
    return {
        "status": "healthy",
        "server": "Weather MCP Server",
        "version": "2.0",
        "api_key_configured": bool(API_KEY),
        "api_status": api_status,
        "available_tools": [
            "get_current_weather",
            "get_weather_by_coordinates", 
            "get_weather_forecast",
            "health_check"
        ]
    }


def run_server(host: str = None, port: int = None, transport: str = None):
    """Run the Weather MCP server"""
    # Use config values if not provided
    if host is None:
        host = config.host
    if port is None:
        port = config.port
    if transport is None:
        transport = config.transport
    
    logger.info(f"Starting Weather MCP server on {host}:{port} with {transport} transport...")
    logger.info("Available tools:")
    logger.info("- get_current_weather: Получение текущей погоды по названию города")
    logger.info("- get_weather_by_coordinates: Получение погоды по координатам")
    logger.info("- get_weather_forecast: Получение прогноза погоды")
    logger.info("- health_check: Проверка состояния сервера")
    
    # Run the server
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    run_server()