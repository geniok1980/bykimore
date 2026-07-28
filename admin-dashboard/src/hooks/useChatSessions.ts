import { useState, useEffect, useCallback } from "react";
import { ChatSession } from "@/components/chat/ChatHistorySidebar";
import { useChatHistory } from "./useChatHistory";

export interface ChatMessage {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
}

export interface ChatSessionData extends ChatSession {
  messages: ChatMessage[];
}

export function useChatSessions() {
  const [currentChatId, setCurrentChatId] = useState<string>("");
  const [chatSessions, setChatSessions] = useState<ChatSessionData[]>([]);
  const [currentMessages, setCurrentMessages] = useState<ChatMessage[]>([]);
  
  // Интеграция с backend API
  const { isLoading, error, loadChatHistory, loadChatById } = useChatHistory();

  // Load sessions from backend and localStorage on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        // Сначала пытаемся загрузить данные с сервера
        const backendSessions = await loadChatHistory();
        
        if (backendSessions && backendSessions.length > 0) {
          // Если есть данные с сервера, используем их
          setChatSessions(backendSessions);
          
          // Проверяем сохраненный текущий чат
          const savedCurrentChatId = localStorage.getItem("currentChatId");
          if (savedCurrentChatId && backendSessions.find(s => s.id === savedCurrentChatId)) {
            setCurrentChatId(savedCurrentChatId);
            const currentSession = backendSessions.find(s => s.id === savedCurrentChatId);
            if (currentSession) {
              setCurrentMessages(currentSession.messages);
            }
          } else if (backendSessions.length > 0) {
            // Используем самый последний чат
            const mostRecent = backendSessions[0]; // уже отсортированы по времени
            setCurrentChatId(mostRecent.id);
            setCurrentMessages(mostRecent.messages);
          }
          
          // Синхронизируем с localStorage
          localStorage.setItem("chatSessionsData", JSON.stringify(backendSessions));
        } else {
          // Fallback к localStorage если нет данных с сервера
          const savedSessions = localStorage.getItem("chatSessionsData");
          const savedCurrentChatId = localStorage.getItem("currentChatId");
          
          if (savedSessions) {
            try {
              const sessions = JSON.parse(savedSessions).map((session: any) => ({
                ...session,
                timestamp: new Date(session.timestamp),
                messages: session.messages.map((msg: any) => ({
                  ...msg,
                  timestamp: new Date(msg.timestamp),
                })),
              }));
              setChatSessions(sessions);
              
              if (savedCurrentChatId && sessions.find((s: ChatSessionData) => s.id === savedCurrentChatId)) {
                setCurrentChatId(savedCurrentChatId);
                const currentSession = sessions.find((s: ChatSessionData) => s.id === savedCurrentChatId);
                if (currentSession) {
                  setCurrentMessages(currentSession.messages);
                }
              } else if (sessions.length > 0) {
                const mostRecent = sessions.sort((a: ChatSessionData, b: ChatSessionData) => 
                  b.timestamp.getTime() - a.timestamp.getTime()
                )[0];
                setCurrentChatId(mostRecent.id);
                setCurrentMessages(mostRecent.messages);
              }
            } catch (error) {
              console.error("Error loading chat sessions from localStorage:", error);
            }
          }
        }
      } catch (error) {
        console.error("Error loading chat data:", error);
        // В случае ошибки загружаем из localStorage
        const savedSessions = localStorage.getItem("chatSessionsData");
        if (savedSessions) {
          try {
            const sessions = JSON.parse(savedSessions).map((session: any) => ({
              ...session,
              timestamp: new Date(session.timestamp),
              messages: session.messages.map((msg: any) => ({
                ...msg,
                timestamp: new Date(msg.timestamp),
              })),
            }));
            setChatSessions(sessions);
          } catch (localError) {
            console.error("Error loading from localStorage:", localError);
          }
        }
      }
    };

    loadData();
  }, [loadChatHistory]);

  // Save sessions to localStorage
  const saveSessions = useCallback((sessions: ChatSessionData[]) => {
    localStorage.setItem("chatSessionsData", JSON.stringify(sessions));
    setChatSessions(sessions);
  }, []);

  // Save current chat ID
  const saveCurrentChatId = useCallback((chatId: string) => {
    localStorage.setItem("currentChatId", chatId);
    setCurrentChatId(chatId);
  }, []);

  // Create a new chat session
  const createNewChat = useCallback(() => {
    const newChatId = `chat_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const newSession: ChatSessionData = {
      id: newChatId,
      title: "Новый чат",
      lastMessage: "",
      timestamp: new Date(),
      messageCount: 0,
      messages: [],
    };

    const updatedSessions = [newSession, ...chatSessions];
    saveSessions(updatedSessions);
    saveCurrentChatId(newChatId);
    setCurrentMessages([]);
    
    return newChatId;
  }, [chatSessions, saveSessions, saveCurrentChatId]);

  // Select a chat session
  const selectChat = useCallback(async (chatId: string) => {
    const session = chatSessions.find(s => s.id === chatId);
    if (session) {
      saveCurrentChatId(chatId);
      
      try {
        // Пытаемся загрузить актуальные сообщения с сервера
        const backendMessages = await loadChatById(chatId);
        if (backendMessages && backendMessages.length > 0) {
          // Обновляем сессию с данными с сервера
          const updatedSession = { ...session, messages: backendMessages };
          const updatedSessions = chatSessions.map(s => 
            s.id === chatId ? updatedSession : s
          );
          setChatSessions(updatedSessions);
          localStorage.setItem("chatSessionsData", JSON.stringify(updatedSessions));
          setCurrentMessages(backendMessages);
        } else {
          // Используем локальные данные
          setCurrentMessages(session.messages);
        }
      } catch (error) {
        console.error("Error loading chat from backend:", error);
        // В случае ошибки используем локальные данные
        setCurrentMessages(session.messages);
      }
    }
  }, [chatSessions, saveCurrentChatId, loadChatById]);

  // Add a message to the current chat
  const addMessage = useCallback((content: string, isUser: boolean) => {
    const newMessage: ChatMessage = {
      id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      content,
      isUser,
      timestamp: new Date(),
    };

    // Use functional state update to avoid dependency on currentMessages
    setCurrentMessages(prevMessages => {
      const updatedMessages = [...prevMessages, newMessage];
      
      // Update the session with the new messages
      setChatSessions(prevSessions => {
        const updatedSessions = prevSessions.map(session => {
          if (session.id === currentChatId) {
            const updatedSession = {
              ...session,
              messages: updatedMessages,
              lastMessage: content,
              timestamp: new Date(),
              messageCount: updatedMessages.length,
              title: session.title === "Новый чат" && updatedMessages.length === 1 && isUser 
                ? content.substring(0, 30) + (content.length > 30 ? "..." : "")
                : session.title,
            };
            return updatedSession;
          }
          return session;
        });
        
        saveSessions(updatedSessions);
        return updatedSessions;
      });
      
      return updatedMessages;
    });
  }, [currentChatId, saveSessions]);

  // Delete a chat session
  const deleteChat = useCallback((chatId: string) => {
    const updatedSessions = chatSessions.filter(session => session.id !== chatId);
    saveSessions(updatedSessions);

    if (currentChatId === chatId) {
      if (updatedSessions.length > 0) {
        const mostRecent = updatedSessions.sort((a, b) => 
          b.timestamp.getTime() - a.timestamp.getTime()
        )[0];
        selectChat(mostRecent.id);
      } else {
        // No sessions left, create a new one
        createNewChat();
      }
    }
  }, [chatSessions, currentChatId, saveSessions, selectChat, createNewChat]);

  // Rename a chat session
  const renameChat = useCallback((chatId: string, newTitle: string) => {
    const updatedSessions = chatSessions.map(session =>
      session.id === chatId ? { ...session, title: newTitle } : session
    );
    saveSessions(updatedSessions);
  }, [chatSessions, saveSessions]);

  // Get simplified sessions for the sidebar
  const getSimplifiedSessions = useCallback((): ChatSession[] => {
    return chatSessions.map(session => ({
      id: session.id,
      title: session.title,
      lastMessage: session.lastMessage,
      timestamp: session.timestamp,
      messageCount: session.messageCount,
    }));
  }, [chatSessions]);

  return {
    currentChatId,
    currentMessages,
    chatSessions: getSimplifiedSessions(),
    createNewChat,
    selectChat,
    addMessage,
    deleteChat,
    renameChat,
    isLoading,
    error,
  };
}