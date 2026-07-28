"use client";

import { useState, useEffect } from "react";
import { BeerExchangeData, BeerExchangeItem } from "@/types/beer-exchange";
import BeerExchangeTable from "@/components/beer-exchange/BeerExchangeTable";
import VideoArea from "@/components/beer-exchange/VideoArea";
import "@/styles/beer-exchange-tv.css";
import { getBeerExchangeItems } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function BeerExchangePage() {
  // Начальное состояние — пустой список блюд, без мок-данных
  const [data, setData] = useState<BeerExchangeData>({
    items: [],
    totalVolume: 0,
    marketTrend: "stable",
    lastUpdated: null,
  });
  const { isAuthenticated } = useAuth();

  // При загрузке страницы получаем агрегированные данные (название, цена, курс)
  useEffect(() => {
    const loadBeerExchange = async () => {
      try {
        const itemsFromApi = await getBeerExchangeItems();
        const sortedById = [...itemsFromApi].sort((a, b) => a.id - b.id);

        let items: BeerExchangeItem[] = sortedById.map((item) => ({
          id: String(item.id),
          name: item.name,
          // Надёжнее считаем распроданным, если бэкенд ставит stoplisted,
          // либо если цена/курс отсутствуют (null) для позиции из стоп-листа
          stoplisted: Boolean(item.stoplisted) || item.price == null || item.rate == null,
          description: "",
          currentPrice: item.price ?? 0,
          priceChange24h: 0,
          priceChangePercentage24h: item.rate ?? 0,
          volume24h: 0,
          category: "main",
          image: "",
          availability: !(Boolean(item.stoplisted) || item.price == null || item.rate == null),
          rating: 0,
          preparationTime: 0,
        }));

        items = items.slice(0, 13);

        setData(prev => ({
          ...prev,
          items,
          totalVolume: items.reduce((sum, i) => sum + i.volume24h, 0),
          // Ставим отметку времени на клиенте, чтобы избежать расхождений при гидрации.
          lastUpdated: Date.now(),
        }));
      } catch (e) {
        console.error("Не удалось загрузить блюда из БД:", e);
      }
    };

    if (isAuthenticated) {
      // Первичная загрузка
      loadBeerExchange();
      // Интервал можно настроить через переменную окружения, по умолчанию 10 сек
      const refreshMsEnv = Number(process.env.NEXT_PUBLIC_BEER_EXCHANGE_REFRESH_MS ?? 10000);
      const refreshMs = Number.isFinite(refreshMsEnv) && refreshMsEnv > 500 ? refreshMsEnv : 10000;
      // Периодическое обновление — тянем реальные данные из БД каждые refreshMs
      const interval = setInterval(loadBeerExchange, refreshMs);
      // Обновляем немедленно при возврате вкладки в фокус/видимость
      const onVisibilityChange = () => {
        if (document.visibilityState === "visible") {
          loadBeerExchange();
        }
      };
      document.addEventListener("visibilitychange", onVisibilityChange);
      return () => {
        clearInterval(interval);
        document.removeEventListener("visibilitychange", onVisibilityChange);
      };
    }
  }, [isAuthenticated]);

  // Убрана имитация случайных изменений — теперь берём только реальные данные из API

  return (
    <div className="tv-dashboard">


       {/* Основной контент - разделение экрана */}
       <div className="tv-main-content">
         {/* Левая часть - Таблица с блюдами */}
         <div className="tv-left-panel">
           <BeerExchangeTable items={data.items} />
         </div>

        {/* Правая часть - Видео трансляция */}
        <div className="tv-right-panel">
          <VideoArea 
            title="Кухня в прямом эфире"
            placeholder="Трансляция с кухни ресторана"
          />
        </div>
      </div>

      {/* Нижняя панель (футер) */}
      <div className="tv-footer">
        <div className="tv-footer-content">
          <div className="tv-stats">
            <div className="tv-stat-item">
              Обновлено: <span suppressHydrationWarning>{
                data.lastUpdated
                  ? new Date(data.lastUpdated).toLocaleTimeString("ru-RU", { hour12: false })
                  : "—"
              }</span>
            </div>
            <div className="tv-stat-item">Позиции на экране: {data.items.length}</div>
          </div>
          <div className="tv-ticker">
            <div className="ticker-content">
              {data.items.length > 0
                ? data.items
                    .map((i) => i.stoplisted ? `${i.name}: РАСПРОДАНО` : `${i.name}: ${Math.round(i.currentPrice)}₽`)
                    .join(" • ")
                : "Данные загружаются…"}
            </div>
          </div>
        </div>
      </div>


    </div>
  );
}