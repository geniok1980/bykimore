"use client";

import React from 'react';

interface ChartData {
  labels: string[];
  values: number[];
}

interface ChartComponentProps {
  title: string;
  data: ChartData;
  type?: 'bar' | 'line';
}

export function ChartComponent({ title, data, type = 'bar' }: ChartComponentProps) {
  const maxValue = Math.max(...data.values);
  
  return (
    <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {title}
      </h3>
      
      <div className="space-y-3">
        {data.labels.map((label, index) => {
          const value = data.values[index];
          const percentage = (value / maxValue) * 100;
          
          return (
            <div key={index} className="flex items-center">
              <div className="w-20 text-sm text-gray-600 dark:text-gray-400 truncate">
                {label}
              </div>
              <div className="flex-1 mx-3">
                <div className="bg-gray-200 dark:bg-gray-700 rounded-full h-4 relative overflow-hidden">
                  <div 
                    className="bg-gradient-to-r from-blue-500 to-purple-600 h-full rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
              <div className="w-16 text-sm font-medium text-gray-900 dark:text-white text-right">
                {value}
              </div>
            </div>
          );
        })}
      </div>
      
      {data.values.length === 0 && (
        <div className="text-center text-gray-500 dark:text-gray-400 py-8">
          Нет данных для отображения
        </div>
      )}
    </div>
  );
}