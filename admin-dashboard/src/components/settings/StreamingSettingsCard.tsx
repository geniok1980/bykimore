"use client";
import { useEffect, useState } from "react";
import { getStreamSettings, upsertStreamSettings, StreamSettingsRead } from "@/lib/api";

export default function StreamingSettingsCard() {
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [hlsUrl, setHlsUrl] = useState<string>("");
  const [active, setActive] = useState<boolean>(true);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const s = await getStreamSettings();
        if (s) {
          setHlsUrl(s.hls_url ?? "");
          setActive(s.active);
        } else {
          // авто-подстановка из env, если настроек ещё нет
          const envUrl = process.env.NEXT_PUBLIC_HLS_URL || "";
          setHlsUrl(envUrl);
          setActive(true);
        }
      } catch (e) {
        console.error(e);
        setError("Не удалось загрузить настройки трансляции");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const validateUrl = (url: string): boolean => {
    if (!url) return true; // пустой допустим, пользователь может деактивировать трансляцию
    try {
      const u = new URL(url);
      return u.protocol === "http:" || u.protocol === "https:";
    } catch {
      return false;
    }
  };

  const handleSave = async () => {
    setSuccess(null);
    if (!validateUrl(hlsUrl)) {
      setError("Некорректный URL. Укажите http(s) ссылку на HLS плейлист (.m3u8).");
      return;
    }
    try {
      setSaving(true);
      setError(null);
      const saved = await upsertStreamSettings({ hls_url: hlsUrl || null, active });
      setSuccess("Настройки сохранены");
    } catch (e) {
      console.error(e);
      setError("Ошибка сохранения настроек");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 shadow-theme-sm">
      <h2 className="text-xl font-semibold text-gray-800 dark:text-white/90 mb-3">Настройки трансляции</h2>

      {loading && (
        <div className="text-sm text-gray-500">Загрузка…</div>
      )}

      {error && (
        <div className="rounded-md bg-red-50 text-red-700 p-3 text-sm mb-3">{error}</div>
      )}

      {success && (
        <div className="rounded-md bg-green-50 text-green-700 p-3 text-sm mb-3">{success}</div>
      )}

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">HLS URL (m3u8)</label>
          <input
            type="url"
            placeholder="https://example.com/live/playlist.m3u8"
            value={hlsUrl}
            onChange={(e) => setHlsUrl(e.target.value)}
            className="w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <p className="mt-1 text-xs text-gray-500">Введите публичный URL HLS потока. Убедитесь, что CORS разрешён на источнике.</p>
        </div>

        <div className="flex items-center gap-2">
          <input
            id="stream-active"
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          <label htmlFor="stream-active" className="text-sm text-gray-700 dark:text-gray-300">Трансляция активна</label>
        </div>

        <div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "Сохранение…" : "Сохранить"}
          </button>
        </div>
      </div>
    </div>
  );
}