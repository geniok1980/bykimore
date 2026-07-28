"use client";
import React, { useEffect, useRef, useState } from 'react';

interface AudioLevelIndicatorProps {
  audioTrack?: MediaStreamTrack | null;
  isActive: boolean;
  className?: string;
}

export const AudioLevelIndicator: React.FC<AudioLevelIndicatorProps> = ({
  audioTrack,
  isActive,
  className = ""
}) => {
  const [audioLevel, setAudioLevel] = useState(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!audioTrack || !isActive) {
      setAudioLevel(0);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      return;
    }

    // Создаем AudioContext и AnalyserNode для анализа аудио
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;
    
    analyserRef.current = analyser;

    // Создаем MediaStream из track и подключаем к анализатору
    const stream = new MediaStream([audioTrack]);
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateAudioLevel = () => {
      if (!analyserRef.current) return;

      analyserRef.current.getByteFrequencyData(dataArray);
      
      // Вычисляем средний уровень звука
      const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length;
      const normalizedLevel = Math.min(average / 128, 1); // Нормализуем к 0-1
      
      setAudioLevel(normalizedLevel);
      
      if (isActive) {
        animationFrameRef.current = requestAnimationFrame(updateAudioLevel);
      }
    };

    updateAudioLevel();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (audioContext.state !== 'closed') {
        audioContext.close();
      }
    };
  }, [audioTrack, isActive]);

  // Создаем массив полосок для визуализации
  const bars = Array.from({ length: 5 }, (_, index) => {
    const threshold = (index + 1) / 5;
    const isActive = audioLevel >= threshold;
    
    return (
      <div
        key={index}
        className={`w-1 rounded-full transition-all duration-100 ${
          isActive 
            ? index < 2 
              ? 'bg-green-500' 
              : index < 4 
              ? 'bg-yellow-500' 
              : 'bg-red-500'
            : 'bg-gray-300 dark:bg-gray-600'
        }`}
        style={{
          height: `${8 + index * 4}px`,
          opacity: isActive ? 1 : 0.3
        }}
      />
    );
  });

  if (!isActive) {
    return null;
  }

  return (
    <div className={`flex items-end gap-1 ${className}`}>
      {bars}
    </div>
  );
};

export default AudioLevelIndicator;