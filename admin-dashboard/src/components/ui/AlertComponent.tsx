"use client";

import React from 'react';

interface AlertComponentProps {
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
}

export function AlertComponent({ type, title, message }: AlertComponentProps) {
  const getAlertStyles = () => {
    switch (type) {
      case 'success':
        return {
          container: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
          icon: '✅',
          titleColor: 'text-green-800 dark:text-green-200',
          messageColor: 'text-green-700 dark:text-green-300'
        };
      case 'warning':
        return {
          container: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
          icon: '⚠️',
          titleColor: 'text-yellow-800 dark:text-yellow-200',
          messageColor: 'text-yellow-700 dark:text-yellow-300'
        };
      case 'error':
        return {
          container: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
          icon: '❌',
          titleColor: 'text-red-800 dark:text-red-200',
          messageColor: 'text-red-700 dark:text-red-300'
        };
      default: // info
        return {
          container: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
          icon: 'ℹ️',
          titleColor: 'text-blue-800 dark:text-blue-200',
          messageColor: 'text-blue-700 dark:text-blue-300'
        };
    }
  };

  const styles = getAlertStyles();

  return (
    <div className={`border rounded-lg p-4 ${styles.container}`}>
      <div className="flex items-start">
        <div className="flex-shrink-0 mr-3 text-lg">
          {styles.icon}
        </div>
        <div className="flex-1">
          <h4 className={`font-medium ${styles.titleColor}`}>
            {title}
          </h4>
          <p className={`mt-1 text-sm ${styles.messageColor}`}>
            {message}
          </p>
        </div>
      </div>
    </div>
  );
}