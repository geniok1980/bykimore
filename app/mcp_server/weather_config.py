"""
Weather MCP Server Configuration
Based on the main project's MCP server configuration structure
"""
import os
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class WeatherMCPServerConfig(BaseModel):
    """Configuration for Weather MCP Server"""
    
    # Server settings
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=7863, description="Server port")
    transport: str = Field(default="stdio", description="Transport protocol (sse, stdio, streamable-http)")
    
    # Authentication settings
    auth_enabled: bool = Field(default=False, description="Enable authentication")
    auth_token: Optional[str] = Field(default=None, description="Authentication token")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Requests per minute")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format"
    )
    
    # Feature toggles
    enable_current_weather: bool = Field(default=True, description="Enable current weather tool")
    enable_weather_forecast: bool = Field(default=True, description="Enable weather forecast tool")
    enable_weather_coordinates: bool = Field(default=True, description="Enable weather by coordinates tool")
    enable_health_check: bool = Field(default=True, description="Enable health check tool")
    
    # External API settings
    openweather_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENWEATHER_API_KEY", ""),
        description="OpenWeatherMap API key"
    )
    openweather_base_url: str = Field(
        default="https://api.openweathermap.org/data/2.5",
        description="OpenWeatherMap API base URL"
    )
    
    # Cache settings
    cache_enabled: bool = Field(default=True, description="Enable response caching")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds (5 minutes)")
    
    # Request timeout settings
    request_timeout: int = Field(default=30, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for failed requests")
    
    # Data validation
    validate_coordinates: bool = Field(default=True, description="Validate latitude/longitude ranges")
    validate_country_codes: bool = Field(default=True, description="Validate ISO country codes")
    
    # Response formatting
    temperature_unit: str = Field(default="celsius", description="Default temperature unit (celsius, fahrenheit, kelvin)")
    include_raw_response: bool = Field(default=False, description="Include raw API response in results")
    
    model_config = ConfigDict(env_prefix="WEATHER_MCP_", case_sensitive=False)


# Global configuration instance
weather_config = WeatherMCPServerConfig()


def get_weather_config() -> WeatherMCPServerConfig:
    """Get the weather MCP server configuration"""
    return weather_config


def validate_config() -> tuple[bool, list[str]]:
    """
    Validate the configuration and return validation status and errors
    
    Returns:
        tuple: (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required API key
    if not weather_config.openweather_api_key:
        errors.append("OPENWEATHER_API_KEY is required but not set")
    
    # Validate port range
    if not (1 <= weather_config.port <= 65535):
        errors.append(f"Port {weather_config.port} is not in valid range (1-65535)")
    
    # Validate transport
    valid_transports = ["sse", "stdio", "streamable-http"]
    if weather_config.transport not in valid_transports:
        errors.append(f"Transport '{weather_config.transport}' not in {valid_transports}")
    
    # Validate temperature unit
    valid_units = ["celsius", "fahrenheit", "kelvin"]
    if weather_config.temperature_unit not in valid_units:
        errors.append(f"Temperature unit '{weather_config.temperature_unit}' not in {valid_units}")
    
    # Validate rate limiting
    if weather_config.rate_limit_enabled:
        if weather_config.rate_limit_requests <= 0:
            errors.append("Rate limit requests must be positive")
        if weather_config.rate_limit_window <= 0:
            errors.append("Rate limit window must be positive")
    
    # Validate cache settings
    if weather_config.cache_enabled and weather_config.cache_ttl <= 0:
        errors.append("Cache TTL must be positive when caching is enabled")
    
    # Validate timeout settings
    if weather_config.request_timeout <= 0:
        errors.append("Request timeout must be positive")
    if weather_config.max_retries < 0:
        errors.append("Max retries cannot be negative")
    
    return len(errors) == 0, errors


def print_config_summary():
    """Print a summary of the current configuration"""
    import sys
    print("Weather MCP Server Configuration:", file=sys.stderr)
    print("=" * 40, file=sys.stderr)
    print(f"Server: {weather_config.host}:{weather_config.port}", file=sys.stderr)
    print(f"Transport: {weather_config.transport}", file=sys.stderr)
    print(f"API Key configured: {'Yes' if weather_config.openweather_api_key else 'No'}", file=sys.stderr)
    print(f"Cache enabled: {weather_config.cache_enabled}", file=sys.stderr)
    print(f"Rate limiting: {weather_config.rate_limit_enabled}", file=sys.stderr)
    print(f"Authentication: {weather_config.auth_enabled}", file=sys.stderr)
    print("=" * 40, file=sys.stderr)


if __name__ == "__main__":
    # Validate and print configuration when run directly
    is_valid, errors = validate_config()
    
    print_config_summary()
    print()
    
    if is_valid:
        print("✅ Configuration is valid")
    else:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")