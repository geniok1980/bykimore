"use client";

import React from 'react';

interface ProgressComponentProps {
  title: string;
  value: number;
  max?: number;
  showPercentage?: boolean;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
}

export function ProgressComponent({ 
  title, 
  value, 
  max = 100, 
  showPercentage = true,
  color = 'blue'
}: ProgressComponentProps) {
  const percentage = Math.min((value / max) * 100, 100);
  
  const getColorClasses = () => {
    switch (color) {
      case 'green':
        return 'bg-green-500';
      case 'yellow':
        return 'bg-yellow-500';
      case 'red':
        return 'bg-red-500';
      case 'purple':
        return 'bg-purple-500';
      default:
        return 'bg-blue-500';
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          {title}
        </h3>
        {showPercentage && (
          <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
            {Math.round(percentage)}%
          </span>
        )}
      </div>
      
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 overflow-hidden">
        <div 
          className={`h-full rounded-full transition-all duration-500 ease-out ${getColorClasses()}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      
      <div className="flex justify-between mt-2 text-sm text-gray-600 dark:text-gray-400">
        <span>{value}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}