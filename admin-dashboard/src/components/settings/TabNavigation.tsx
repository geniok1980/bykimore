"use client";
import React from "react";

export type TabType = "general" | "iiko-integration" | "users";

interface TabNavigationProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
}

const TabNavigation: React.FC<TabNavigationProps> = ({ activeTab, onTabChange }) => {
  const getButtonClass = (tab: TabType) =>
    activeTab === tab
      ? "shadow-theme-xs text-gray-900 dark:text-white bg-white dark:bg-gray-800"
      : "text-gray-500 dark:text-gray-400";

  return (
    <div className="flex items-center gap-0.5 rounded-lg bg-gray-100 p-0.5 dark:bg-gray-900 mb-6">
      <button
        onClick={() => onTabChange("general")}
        className={`px-4 py-2.5 font-medium w-full rounded-md text-sm hover:text-gray-900 dark:hover:text-white transition-colors ${getButtonClass(
          "general"
        )}`}
      >
        Общие настройки
      </button>

      <button
        onClick={() => onTabChange("iiko-integration")}
        className={`px-4 py-2.5 font-medium w-full rounded-md text-sm hover:text-gray-900 dark:hover:text-white transition-colors ${getButtonClass(
          "iiko-integration"
        )}`}
      >
        Интеграция iiko
      </button>

      <button
        onClick={() => onTabChange("users")}
        className={`px-4 py-2.5 font-medium w-full rounded-md text-sm hover:text-gray-900 dark:hover:text-white transition-colors ${getButtonClass(
          "users"
        )}`}
      >
        Пользователи
      </button>

    </div>
  );
};

export default TabNavigation;