"use client";

import { useState, useCallback } from 'react';
import { Message } from 'ai';

interface UIComponent {
  type: string;
  data: any;
  props?: any;
}

interface ExtendedMessage extends Message {
  ui_components?: UIComponent[];
}

interface UseChatWithUIOptions {
  api: string;
  headers?: Record<string, string>;
  onFinish?: (message: ExtendedMessage) => void;
}

export function useChatWithUI({ api, headers, onFinish }: UseChatWithUIOptions) {
  const [messages, setMessages] = useState<ExtendedMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setInput(e.target.value);
  }, []);

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;

    console.log('💬 === SENDING MESSAGE ===');
    console.log('💬 Input:', input);
    console.log('💬 API endpoint:', api);

    const userMessage: ExtendedMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input,
      createdAt: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      console.log('💬 Sending request to API...');
      const response = await fetch(api, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        body: JSON.stringify({
          messages: [...messages, userMessage].map(m => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      console.log('💬 Response status:', response.status);
      if (!response.ok) {
        console.log('💬 ❌ API request failed:', response.status, response.statusText);
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      console.log('💬 ✅ API request successful, starting to read stream...');
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No reader available');
      }

      const assistantMessage: ExtendedMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        createdAt: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            if (jsonStr === '[DONE]') continue;

            try {
              const parsed = JSON.parse(jsonStr);
              
              if (parsed.ui_components) {
                // Handle UI components
                setMessages(prev => prev.map(m => 
                  m.id === assistantMessage.id 
                    ? { ...m, ui_components: parsed.ui_components }
                    : m
                ));
              } else if (parsed.choices?.[0]?.delta?.content) {
                // Handle text content
                const content = parsed.choices[0].delta.content;
                setMessages(prev => prev.map(m => 
                  m.id === assistantMessage.id 
                    ? { ...m, content: (m.content || '') + content }
                    : m
                ));
              }
            } catch (error) {
              console.error('Error parsing streaming data:', error);
            }
          }
        }
      }

      // Call onFinish callback
      setMessages(prev => {
        const finalMessage = prev.find(m => m.id === assistantMessage.id);
        if (finalMessage && onFinish) {
          onFinish(finalMessage);
        }
        return prev;
      });

    } catch (error) {
      console.error('Error in chat:', error);
      
      // Add error message
      const errorMessage: ExtendedMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Извините, произошла ошибка при обработке вашего запроса.',
        createdAt: new Date(),
      };
      
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, messages, api, headers, onFinish]);

  return {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
  };
}