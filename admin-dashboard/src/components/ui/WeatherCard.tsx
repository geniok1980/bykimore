"use client";

import React from 'react';

interface WeatherCardProps {
  location: string;
  temperature: number;
  condition: string;
  humidity?: number;
  wind_speed?: number;
  icon?: string;
}

export function WeatherCard({ 
  location, 
  temperature, 
  condition, 
  humidity, 
  wind_speed, 
  icon 
}: WeatherCardProps) {
  return (
    <div className="bg-gradient-to-br from-blue-400 to-blue-600 text-white p-6 rounded-lg shadow-lg max-w-sm">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold">{location}</h3>
          <p className="text-blue-100 text-sm">{condition}</p>
        </div>
        {icon && (
          <div className="text-4xl">
            {getWeatherIcon(icon)}
          </div>
        )}
      </div>
      
      <div className="mb-4">
        <span className="text-4xl font-bold">{temperature}°</span>
        <span className="text-blue-100 ml-1">C</span>
      </div>
      
      {(humidity !== undefined || wind_speed !== undefined) && (
        <div className="flex justify-between text-sm text-blue-100">
          {humidity !== undefined && (
            <div className="flex items-center">
              <span className="mr-1">💧</span>
              <span>{humidity}%</span>
            </div>
          )}
          {wind_speed !== undefined && (
            <div className="flex items-center">
              <span className="mr-1">💨</span>
              <span>{wind_speed} м/с</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function getWeatherIcon(condition: string): string {
  const iconMap: { [key: string]: string } = {
    'sunny': '☀️',
    'cloudy': '☁️',
    'rainy': '🌧️',
    'snowy': '❄️',
    'stormy': '⛈️',
    'partly_cloudy': '⛅',
    'clear': '🌙',
    'fog': '🌫️',
  };
  
  return iconMap[condition.toLowerCase()] || '🌤️';
}