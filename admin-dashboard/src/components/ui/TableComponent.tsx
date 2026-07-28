"use client";

import React from 'react';

interface TableComponentProps {
  title: string;
  headers: string[];
  rows: (string | number)[][];
}

export function TableComponent({ title, headers, rows }: TableComponentProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          {title}
        </h3>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-700">
            <tr>
              {headers.map((header, index) => (
                <th 
                  key={index}
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {rows.map((row, rowIndex) => (
              <tr 
                key={rowIndex}
                className="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                {row.map((cell, cellIndex) => (
                  <td 
                    key={cellIndex}
                    className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {rows.length === 0 && (
        <div className="text-center text-gray-500 dark:text-gray-400 py-8">
          Нет данных для отображения
        </div>
      )}
    </div>
  );
}