"use client";

import React from 'react';

interface CardComponentProps {
  title: string;
  content: string;
  footer?: string;
  variant?: 'default' | 'outlined' | 'elevated';
}

export function CardComponent({ 
  title, 
  content, 
  footer, 
  variant = 'default' 
}: CardComponentProps) {
  const getVariantClasses = () => {
    switch (variant) {
      case 'outlined':
        return 'border-2 border-gray-300 dark:border-gray-600 bg-transparent';
      case 'elevated':
        return 'shadow-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800';
      default:
        return 'shadow-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800';
    }
  };

  return (
    <div className={`rounded-lg p-6 ${getVariantClasses()}`}>
      <div className="mb-4">
        <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
          {title}
        </h3>
      </div>
      
      <div className="mb-4">
        <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
          {content}
        </p>
      </div>
      
      {footer && (
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {footer}
          </p>
        </div>
      )}
    </div>
  );
}