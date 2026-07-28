"use client";

import React from 'react';
import { WeatherCard } from './WeatherCard';
import { ChartComponent } from './ChartComponent';
import { TableComponent } from './TableComponent';
import { AlertComponent } from './AlertComponent';
import { ProgressComponent } from './ProgressComponent';
import { CardComponent } from './CardComponent';

interface UIComponent {
  type: string;
  data: any;
  props?: any;
}

interface GenerativeUIProps {
  components: UIComponent[];
}

export function GenerativeUI({ components }: GenerativeUIProps) {
  if (!components || components.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {components.map((component, index) => (
        <UIComponentRenderer key={index} component={component} />
      ))}
    </div>
  );
}

function UIComponentRenderer({ component }: { component: UIComponent }) {
  const { type, data, props } = component;

  switch (type) {
    case 'weather_card':
      return <WeatherCard {...data} {...props} />;
    
    case 'chart':
      return <ChartComponent {...data} {...props} />;
    
    case 'table':
      return <TableComponent {...data} {...props} />;
    
    case 'alert':
      return <AlertComponent {...data} {...props} />;
    
    case 'progress':
      return <ProgressComponent {...data} {...props} />;
    
    case 'card':
      return <CardComponent {...data} {...props} />;
    
    default:
      console.warn(`Unknown UI component type: ${type}`);
      return (
        <div className="p-4 border border-gray-200 rounded-lg bg-gray-50">
          <p className="text-sm text-gray-600">
            Неизвестный тип компонента: {type}
          </p>
          <pre className="mt-2 text-xs text-gray-500 overflow-auto">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      );
  }
}