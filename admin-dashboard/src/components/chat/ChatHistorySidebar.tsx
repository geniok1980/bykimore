"use client";
import React, { useState, useEffect } from "react";
import { PlusIcon, TrashBinIcon, PencilIcon } from "@/icons";

export interface ChatSession {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: Date;
  messageCount: number;
}

interface ChatHistorySidebarProps {
  currentChatId: string;
  chatSessions: ChatSession[];
  onChatSelect: (chatId: string) => void;
  onNewChat: () => void;
  onDeleteChat: (chatId: string) => void;
  onRenameChat: (chatId: string, newTitle: string) => void;
}

export default function ChatHistorySidebar({
  currentChatId,
  chatSessions,
  onChatSelect,
  onNewChat,
  onDeleteChat,
  onRenameChat,
}: ChatHistorySidebarProps) {
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const handleDeleteChat = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onDeleteChat(chatId);
  };

  const handleStartEdit = (chatId: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingChatId(chatId);
    setEditTitle(currentTitle);
  };

  const handleSaveEdit = (chatId: string) => {
    if (editTitle.trim()) {
      onRenameChat(chatId, editTitle.trim());
    }
    setEditingChatId(null);
    setEditTitle("");
  };

  const handleCancelEdit = () => {
    setEditingChatId(null);
    setEditTitle("");
  };

  const formatTimestamp = (timestamp: Date) => {
    const now = new Date();
    const diff = now.getTime() - timestamp.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
      return "Сегодня";
    } else if (days === 1) {
      return "Вчера";
    } else if (days < 7) {
      return `${days} дн. назад`;
    } else {
      return timestamp.toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "short",
      });
    }
  };

  const truncateText = (text: string, maxLength: number = 30) => {
    return text.length > maxLength ? text.substring(0, maxLength) + "..." : text;
  };

  return (
    <div className="w-80 h-full bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-800 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-800">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-brand-500 hover:bg-brand-600 text-white rounded-lg transition-colors"
        >
          <PlusIcon />
          <span>Новый чат</span>
        </button>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-y-auto p-2">
        <div className="space-y-1">
          {chatSessions.length === 0 ? (
            <div className="text-center text-gray-500 dark:text-gray-400 py-8">
              <p>История чатов пуста</p>
              <p className="text-sm mt-1">Начните новый разговор</p>
            </div>
          ) : (
            chatSessions
              .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
              .map((session) => (
                <div
                  key={session.id}
                  onClick={() => onChatSelect(session.id)}
                  className={`group relative p-3 rounded-lg cursor-pointer transition-colors ${
                    currentChatId === session.id
                      ? "bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800"
                      : "hover:bg-gray-50 dark:hover:bg-gray-800"
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      {editingChatId === session.id ? (
                        <input
                          type="text"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          onBlur={() => handleSaveEdit(session.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              handleSaveEdit(session.id);
                            } else if (e.key === "Escape") {
                              handleCancelEdit();
                            }
                          }}
                          className="w-full px-2 py-1 text-sm font-medium bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
                          autoFocus
                          onClick={(e) => e.stopPropagation()}
                        />
                      ) : (
                        <h3 className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {session.title}
                        </h3>
                      )}
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">
                        {truncateText(session.lastMessage)}
                      </p>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-gray-400 dark:text-gray-500">
                          {formatTimestamp(session.timestamp)}
                        </span>
                        <span className="text-xs text-gray-400 dark:text-gray-500">
                          {session.messageCount} сообщ.
                        </span>
                      </div>
                    </div>
                    
                    {/* Action buttons */}
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2">
                      <button
                        onClick={(e) => handleStartEdit(session.id, session.title, e)}
                        className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded"
                        title="Переименовать"
                      >
                        <PencilIcon />
                      </button>
                      <button
                        onClick={(e) => handleDeleteChat(session.id, e)}
                        className="p-1 text-gray-400 hover:text-red-500 rounded"
                        title="Удалить"
                      >
                        <TrashBinIcon />
                      </button>
                    </div>
                  </div>
                </div>
              ))
          )}
        </div>
      </div>
    </div>
  );
}