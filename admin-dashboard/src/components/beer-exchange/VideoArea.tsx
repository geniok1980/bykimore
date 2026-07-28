"use client";
import { useEffect, useMemo, useState } from "react";
import HlsPlayer from "@/components/video/HlsPlayer";
import { getStreamSettings } from "@/lib/api";

interface VideoAreaProps {
  title?: string;
  placeholder?: string;
}

export default function VideoArea({
  title = "Прямая трансляция",
  placeholder = "Здесь будет видео трансляция",
}: VideoAreaProps) {
  const [hlsUrl, setHlsUrl] = useState<string | null>(null);
  const [active, setActive] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSettings = async () => {
      try {
        setLoading(true);
        setError(null);
        const settings = await getStreamSettings();
        if (settings) {
          setHlsUrl(settings.hls_url ?? null);
          setActive(settings.active);
        } else {
          // Фолбэк: используем переменную окружения, если настроек ещё нет
          const envUrl = process.env.NEXT_PUBLIC_HLS_URL || null;
          setHlsUrl(envUrl);
          setActive(true);
        }
      } catch (e) {
        console.error("Не удалось загрузить настройки трансляции:", e);
        setError("Ошибка загрузки настроек трансляции");
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
  }, []);

  const canShowPlayer = useMemo(() => {
    return active && !!hlsUrl;
  }, [active, hlsUrl]);

  return (
    <div className="tv-video-container">
      <div className="tv-video-content">
        {/* Заголовок поверх видео, чтобы не съедать место */}
        <div className="absolute top-2 left-2 z-10 bg-black/40 text-white rounded-md px-3 py-1 backdrop-blur-sm flex items-center gap-3">
          <h3 className="text-sm sm:text-base font-semibold">{title}</h3>
          {loading && <span className="text-xs opacity-80">Загрузка…</span>}
        </div>

        {error && (
          <div className="rounded-md bg-red-50 text-red-700 p-3 text-sm mb-2">
            {error}
          </div>
        )}

        {canShowPlayer ? (
          <HlsPlayer
            src={hlsUrl!}
            autoPlay={true}
            muted={true}
            controls={true}
            className="absolute inset-0 w-full h-full rounded-none"
          />
        ) : (
          <div className="video-placeholder">
            <div className="video-icon">📹</div>
            <div className="video-text">{placeholder}</div>
            <div className="video-subtitle">
              {hlsUrl ? (
                <>Трансляция неактивна. Включите её в настройках.</>
              ) : (
                <>Подключите источник видео (HLS URL) в настройках трансляции.</>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}