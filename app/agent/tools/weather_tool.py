"""
Weather Tools with Generative UI Support
Provides weather functionality with UI components for the chat interface
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from app.mcp_client.weather_client import WeatherMCPClient

logger = logging.getLogger(__name__)


class WeatherTools:
    """Weather tools with generative UI support"""
    
    def __init__(self):
        self.client = WeatherMCPClient()
        self._weather_descriptions_ru = {
            "Clear": "Ясно",
            "Clouds": "Облачно", 
            "Rain": "Дождь",
            "Drizzle": "Морось",
            "Thunderstorm": "Гроза",
            "Snow": "Снег",
            "Mist": "Туман",
            "Smoke": "Дым",
            "Haze": "Дымка",
            "Dust": "Пыль",
            "Fog": "Туман",
            "Sand": "Песок",
            "Ash": "Пепел",
            "Squall": "Шквал",
            "Tornado": "Торнадо"
        }
    
    def _translate_weather_description(self, description: str) -> str:
        """Translate weather description to Russian"""
        for en, ru in self._weather_descriptions_ru.items():
            if en.lower() in description.lower():
                return ru
        return description
    
    def _get_weather_icon_emoji(self, icon_code: str) -> str:
        """Get emoji for weather icon"""
        icon_map = {
            "01d": "☀️",  # clear sky day
            "01n": "🌙",  # clear sky night
            "02d": "⛅",  # few clouds day
            "02n": "☁️",  # few clouds night
            "03d": "☁️",  # scattered clouds
            "03n": "☁️",
            "04d": "☁️",  # broken clouds
            "04n": "☁️",
            "09d": "🌧️",  # shower rain
            "09n": "🌧️",
            "10d": "🌦️",  # rain day
            "10n": "🌧️",  # rain night
            "11d": "⛈️",  # thunderstorm
            "11n": "⛈️",
            "13d": "🌨️",  # snow
            "13n": "🌨️",
            "50d": "🌫️",  # mist
            "50n": "🌫️"
        }
        return icon_map.get(icon_code, "🌤️")
    
    def _format_temperature(self, temp: float, units: str) -> str:
        """Format temperature with units"""
        if units == "metric":
            return f"{temp:.1f}°C"
        elif units == "imperial":
            return f"{temp:.1f}°F"
        else:  # kelvin
            return f"{temp:.1f}K"
    
    def _create_weather_card_ui(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create weather card UI component"""
        if "error" in weather_data:
            return {
                "type": "alert",
                "variant": "destructive",
                "title": "Ошибка получения погоды",
                "description": weather_data["error"]
            }
        
        location = weather_data.get("location", {})
        weather = weather_data.get("weather", {})
        wind = weather_data.get("wind", {})
        units = weather_data.get("units", "metric")
        
        city = location.get("city", "Неизвестно")
        country = location.get("country", "")
        temp = weather.get("temperature", 0)
        feels_like = weather.get("feels_like", 0)
        humidity = weather.get("humidity", 0)
        pressure = weather.get("pressure", 0)
        wind_speed = wind.get("speed", 0)
        description = weather.get("description", "")
        icon = weather.get("icon", "01d")
        
        # Translate description
        description_ru = self._translate_weather_description(description)
        
        # Get emoji
        emoji = self._get_weather_icon_emoji(icon)
        
        return {
            "type": "weather_card",
            "data": {
                "location": f"{city}, {country}",
                "temperature": self._format_temperature(temp, units),
                "feels_like": self._format_temperature(feels_like, units),
                "description": description_ru,
                "emoji": emoji,
                "humidity": f"{humidity}%",
                "pressure": f"{pressure} гПа",
                "wind_speed": f"{wind_speed} м/с" if units == "metric" else f"{wind_speed} миль/ч",
                "timestamp": datetime.now().strftime("%H:%M")
            }
        }
    
    def _create_forecast_chart_ui(self, forecast_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create forecast chart UI component"""
        if "error" in forecast_data:
            return {
                "type": "alert",
                "variant": "destructive", 
                "title": "Ошибка получения прогноза",
                "description": forecast_data["error"]
            }
        
        location = forecast_data.get("location", {})
        forecasts = forecast_data.get("forecasts", [])
        units = forecast_data.get("units", "metric")
        
        # Group forecasts by day
        daily_forecasts = {}
        for forecast in forecasts[:24]:  # Take first 24 hours (3 days)
            dt = datetime.fromtimestamp(forecast["datetime"])
            day_key = dt.strftime("%Y-%m-%d")
            
            if day_key not in daily_forecasts:
                daily_forecasts[day_key] = {
                    "date": dt.strftime("%d.%m"),
                    "day_name": dt.strftime("%A"),
                    "temps": [],
                    "descriptions": [],
                    "icons": []
                }
            
            daily_forecasts[day_key]["temps"].append(forecast["weather"]["temperature"])
            daily_forecasts[day_key]["descriptions"].append(forecast["weather"]["description"])
            daily_forecasts[day_key]["icons"].append(forecast["weather"]["icon"])
        
        # Create chart data
        chart_data = []
        for day_data in list(daily_forecasts.values())[:5]:  # Max 5 days
            avg_temp = sum(day_data["temps"]) / len(day_data["temps"])
            most_common_icon = max(set(day_data["icons"]), key=day_data["icons"].count)
            most_common_desc = max(set(day_data["descriptions"]), key=day_data["descriptions"].count)
            
            chart_data.append({
                "date": day_data["date"],
                "temperature": round(avg_temp, 1),
                "description": self._translate_weather_description(most_common_desc),
                "emoji": self._get_weather_icon_emoji(most_common_icon)
            })
        
        return {
            "type": "forecast_chart",
            "data": {
                "location": f"{location.get('city', 'Неизвестно')}, {location.get('country', '')}",
                "forecasts": chart_data,
                "units": "°C" if units == "metric" else ("°F" if units == "imperial" else "K")
            }
        }
    
    async def get_weather_tool_func(self, city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
        """
        Get current weather with UI component
        
        Args:
            city: City name
            country_code: Country code (optional)
            units: Units (metric, imperial, kelvin)
            
        Returns:
            Weather data with UI component
        """
        try:
            # Connect to weather client
            if not await self.client.connect():
                return {
                    "text_response": "Не удалось подключиться к сервису погоды",
                    "ui_components": [{
                        "type": "alert",
                        "variant": "destructive",
                        "title": "Ошибка подключения",
                        "description": "Не удалось подключиться к сервису погоды"
                    }]
                }
            
            # Get weather data
            weather_data = await self.client.get_current_weather(city, country_code, units)
            
            # Create UI component
            ui_component = self._create_weather_card_ui(weather_data)
            
            # Create text response
            if "error" in weather_data:
                text_response = f"Ошибка получения погоды для {city}: {weather_data['error']}"
            else:
                location = weather_data.get("location", {})
                weather = weather_data.get("weather", {})
                city_name = location.get("city", city)
                country_name = location.get("country", "")
                temp = self._format_temperature(weather.get("temperature", 0), units)
                description = self._translate_weather_description(weather.get("description", ""))
                
                text_response = f"Текущая погода в {city_name}, {country_name}: {temp}, {description}"
            
            return {
                "text_response": text_response,
                "ui_components": [ui_component]
            }
            
        except Exception as e:
            logger.error(f"Error getting weather: {e}")
            return {
                "text_response": f"Произошла ошибка при получении погоды: {str(e)}",
                "ui_components": [{
                    "type": "alert",
                    "variant": "destructive",
                    "title": "Ошибка",
                    "description": str(e)
                }]
            }
        finally:
            await self.client.disconnect()
    
    async def get_weather_forecast_tool(self, city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
        """
        Get weather forecast with UI component
        
        Args:
            city: City name
            country_code: Country code (optional)
            days: Number of days (1-5)
            units: Units (metric, imperial, kelvin)
            
        Returns:
            Forecast data with UI component
        """
        try:
            # Connect to weather client
            if not await self.client.connect():
                return {
                    "text_response": "Не удалось подключиться к сервису погоды",
                    "ui_components": [{
                        "type": "alert",
                        "variant": "destructive",
                        "title": "Ошибка подключения",
                        "description": "Не удалось подключиться к сервису погоды"
                    }]
                }
            
            # Get forecast data
            forecast_data = await self.client.get_weather_forecast(city, country_code, days, units)
            
            # Create UI components
            ui_components = []
            
            # Add current weather if available
            if "forecasts" in forecast_data and forecast_data["forecasts"]:
                current_forecast = forecast_data["forecasts"][0]
                current_weather_data = {
                    "location": forecast_data.get("location", {}),
                    "weather": current_forecast.get("weather", {}),
                    "wind": current_forecast.get("wind", {}),
                    "units": forecast_data.get("units", units)
                }
                ui_components.append(self._create_weather_card_ui(current_weather_data))
            
            # Add forecast chart
            ui_components.append(self._create_forecast_chart_ui(forecast_data))
            
            # Create text response
            if "error" in forecast_data:
                text_response = f"Ошибка получения прогноза для {city}: {forecast_data['error']}"
            else:
                location = forecast_data.get("location", {})
                city_name = location.get("city", city)
                country_name = location.get("country", "")
                days_requested = forecast_data.get("days_requested", days)
                
                text_response = f"Прогноз погоды на {days_requested} дней для {city_name}, {country_name}"
            
            return {
                "text_response": text_response,
                "ui_components": ui_components
            }
            
        except Exception as e:
            logger.error(f"Error getting forecast: {e}")
            return {
                "text_response": f"Произошла ошибка при получении прогноза: {str(e)}",
                "ui_components": [{
                    "type": "alert",
                    "variant": "destructive",
                    "title": "Ошибка",
                    "description": str(e)
                }]
            }
        finally:
            await self.client.disconnect()


# Global instance
weather_tools = WeatherTools()

# Export functions for use in agents
async def get_weather_tool_func(city: str, country_code: Optional[str] = None, units: str = "metric") -> Dict[str, Any]:
    """Get current weather with UI component"""
    return await weather_tools.get_weather_tool_func(city, country_code, units)

async def get_weather_forecast_tool(city: str, country_code: Optional[str] = None, days: int = 5, units: str = "metric") -> Dict[str, Any]:
    """Get weather forecast with UI component"""
    return await weather_tools.get_weather_forecast_tool(city, country_code, days, units)