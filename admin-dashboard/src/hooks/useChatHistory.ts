import { useState, useEffect, useCallback } from "react";
import { getChatHistory, getChatById, ChatMessage as ApiChatMessage, ChatHistoryResponse } from "@/lib/api";
import { ChatMessage, ChatSessionData } from "./useChatSessions";

export interface ChatHistoryHook {
  isLoading: boolean;
  error: string | null;
  loadChatHistory: () => Promise<ChatSessionData[]>;
  loadChatById: (chatId: string) => Promise<ChatMessage[]>;
  syncWithLocalStorage: (localSessions: ChatSessionData[]) => ChatSessionData[];
}

// Функция для преобразования API сообщения в локальный формат
function convertApiMessageToLocal(apiMessage: ApiChatMessage): ChatMessage[] {
  const messages: ChatMessage[] = [];
  
  // Добавляем пользовательское сообщение
  if (apiMessage.user_message) {
    messages.push({
      id: `${apiMessage.id}_user`,
      content: apiMessage.user_message,
      isUser: true,
      timestamp: new Date(apiMessage.timestamp),
    });
  }
  
  // Добавляем ответ ассистента
  if (apiMessage.assistant_message) {
    messages.push({
      id: `${apiMessage.id}_assistant`,
      content: apiMessage.assistant_message,
      isUser: false,
      timestamp: new Date(apiMessage.timestamp),
    });
  }
  
  return messages;
}

// Функция для группировки сообщений по chat_id
function groupMessagesByChatId(apiMessages: ApiChatMessage[]): Map<string, ChatMessage[]> {
  const grouped = new Map<string, ChatMessage[]>();
  
  apiMessages.forEach(apiMessage => {
    const chatId = apiMessage.chat_id;
    const localMessages = convertApiMessageToLocal(apiMessage);
    
    if (grouped.has(chatId)) {
      grouped.get(chatId)!.push(...localMessages);
    } else {
      grouped.set(chatId, localMessages);
    }
  });
  
  // Сортируем сообщения в каждом чате по времени
  grouped.forEach(messages => {
    messages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
  });
  
  return grouped;
}

export function useChatHistory(): ChatHistoryHook {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadChatHistory = useCallback(async (): Promise<ChatSessionData[]> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response: ChatHistoryResponse = await getChatHistory();
      
      // Группируем сообщения по chat_id
      const groupedMessages = groupMessagesByChatId(response.messages);
      
      // Преобразуем в формат ChatSessionData
      const backendSessions: ChatSessionData[] = Array.from(groupedMessages.entries()).map(([chatId, messages]) => {
        const firstMessage = messages.find(m => m.isUser);
        const lastMessage = messages[messages.length - 1];
        
        return {
          id: chatId,
          title: firstMessage?.content ? 
            (firstMessage.content.slice(0, 50) + (firstMessage.content.length > 50 ? "..." : "")) : 
            "Новый чат",
          lastMessage: lastMessage?.content || "",
          timestamp: lastMessage?.timestamp || new Date(),
          messageCount: messages.length,
          messages,
        };
      });
      
      // Сортируем сессии по времени (новые сначала)
      backendSessions.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
      
      return backendSessions;
    } catch (err) {
      let errorMessage = "Ошибка загрузки истории чатов";
      
      if (err instanceof Error) {
        // Проверяем на ошибки аутентификации
        if (err.message.includes("401") || err.message.includes("Unauthorized")) {
          errorMessage = "Ошибка аутентификации. Пожалуйста, войдите в систему.";
        } else if (err.message.includes("403") || err.message.includes("Forbidden")) {
          errorMessage = "Недостаточно прав доступа.";
        } else if (err.message.includes("Failed to retrieve chat history")) {
          errorMessage = "Не удалось загрузить историю чатов. Проверьте подключение к серверу.";
        } else {
          errorMessage = err.message;
        }
      }
      
      setError(errorMessage);
      console.error("Ошибка загрузки истории чатов:", err);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadChatById = useCallback(async (chatId: string): Promise<ChatMessage[]> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response: ChatHistoryResponse = await getChatById(chatId);
      const allMessages: ChatMessage[] = [];
      
      response.messages.forEach(apiMessage => {
        allMessages.push(...convertApiMessageToLocal(apiMessage));
      });
      
      // Сортируем по времени
      allMessages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
      
      return allMessages;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Ошибка загрузки чата";
      setError(errorMessage);
      console.error("Ошибка загрузки чата:", err);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const syncWithLocalStorage = useCallback((localSessions: ChatSessionData[]): ChatSessionData[] => {
    // Эта функция будет объединять локальные данные с данными с сервера
    // Пока возвращаем локальные данные как есть
    // В будущем здесь можно добавить логику синхронизации
    return localSessions;
  }, []);

  return {
    isLoading,
    error,
    loadChatHistory,
    loadChatById,
    syncWithLocalStorage,
  };
}