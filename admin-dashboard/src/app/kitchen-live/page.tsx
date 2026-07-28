"use client";
import React, { useState } from "react";
import HlsPlayer from "@/components/video/HlsPlayer";

const defaultUrl = process.env.NEXT_PUBLIC_HLS_URL || "";

export default function KitchenLivePage() {
  const [url, setUrl] = useState<string>(defaultUrl);
  const [inputVal, setInputVal] = useState<string>(defaultUrl);
  const [error, setError] = useState<string>("");

  const handlePlay = () => {
    setError("");
    if (!inputVal || !/^https?:\/\//i.test(inputVal)) {
      setError("Введите корректный URL потока (http/https)");
      return;
    }
    setUrl(inputVal.trim());
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Прямая трансляция с кухни</h1>

      <div className="mb-4 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2">
        <input
          type="text"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          placeholder="Введите URL HLS (.m3u8)"
          className="h-11 w-full rounded-lg border appearance-none px-4 py-2.5 text-sm shadow-theme-xs placeholder:text-gray-400 focus:outline-hidden focus:ring-3 bg-transparent text-gray-800 border-gray-300 focus:border-brand-300 focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
        />
        <button
          onClick={handlePlay}
          className="px-4 py-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700"
        >
          Смотреть
        </button>
      </div>

      {error && <p className="text-red-600 mb-3 text-sm">{error}</p>}

      {url ? (
        <HlsPlayer src={url} autoPlay muted={false} controls className="w-full aspect-video rounded-xl bg-black" />
      ) : (
        <div className="w-full aspect-video rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-gray-500">
          Укажите URL потока HLS (.m3u8), чтобы начать трансляцию
        </div>
      )}
    </div>
  );
}