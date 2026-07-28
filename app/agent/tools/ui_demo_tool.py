"""
Демонстрационный инструмент для генеративного UI
"""
from typing import Dict, Any, List
from app.schemas.chat import UIComponent


class UIDemoTool:
    """Инструмент для демонстрации генеративного UI"""
    
    @staticmethod
    def create_weather_card(location: str, temperature: int, description: str) -> UIComponent:
        """Создает карточку погоды"""
        return UIComponent(
            type="weather_card",
            data={
                "location": location,
                "temperature": temperature,
                "description": description,
                "humidity": 65,
                "feels_like": temperature + 2,
                "wind_speed": 10,
                "pressure": 1013
            }
        )
    
    @staticmethod
    def create_chart_component(chart_type: str, data: List[Dict[str, Any]]) -> UIComponent:
        """Создает компонент графика"""
        return UIComponent(
            type="chart",
            data={
                "chart_type": chart_type,
                "data": data,
                "title": f"{chart_type.title()} Chart",
                "x_axis": "Date",
                "y_axis": "Value"
            }
        )
    
    @staticmethod
    def create_table_component(headers: List[str], rows: List[List[str]]) -> UIComponent:
        """Создает компонент таблицы"""
        return UIComponent(
            type="table",
            data={
                "headers": headers,
                "rows": rows,
                "sortable": True,
                "searchable": True
            }
        )
    
    @staticmethod
    def create_alert_component(message: str, alert_type: str = "info") -> UIComponent:
        """Создает компонент уведомления"""
        return UIComponent(
            type="alert",
            data={
                "message": message,
                "type": alert_type,  # info, warning, error, success
                "dismissible": True
            }
        )
    
    @staticmethod
    def create_progress_component(value: int, max_value: int = 100, label: str = "") -> UIComponent:
        """Создает компонент прогресс-бара"""
        return UIComponent(
            type="progress",
            data={
                "value": value,
                "max": max_value,
                "percentage": round((value / max_value) * 100, 1),
                "label": label,
                "color": "blue" if value < 70 else "green" if value < 90 else "red"
            }
        )
    
    @staticmethod
    def create_card_component(title: str, content: str, actions: List[Dict[str, str]] = None) -> UIComponent:
        """Создает компонент карточки"""
        return UIComponent(
            type="card",
            data={
                "title": title,
                "content": content,
                "actions": actions or [],
                "timestamp": "2024-01-15T10:30:00Z"
            }
        )