"use client";

import { BeerExchangeData } from "@/types/beer-exchange";

interface BeerExchangeStatsProps {
  data: BeerExchangeData;
}

export default function BeerExchangeStats({ data }: BeerExchangeStatsProps) {
  const gainers = data.items.filter(item => item.priceChangePercentage24h > 0).length;
  const losers = data.items.filter(item => item.priceChangePercentage24h < 0).length;
  const stable = data.items.filter(item => item.priceChangePercentage24h === 0).length;
  
  const avgPriceChange = data.items.reduce((sum, item) => sum + item.priceChangePercentage24h, 0) / data.items.length;
  const totalValue = data.items.reduce((sum, item) => sum + (item.currentPrice * item.volume24h), 0);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency: "RUB",
      minimumFractionDigits: 0,
    }).format(value);
  };

  const formatPercentage = (percentage: number) => {
    const sign = percentage > 0 ? "+" : "";
    return `${sign}${percentage.toFixed(1)}%`;
  };

  // Форматированное время обновления: число (timestamp) -> локальное время
  const formattedLastUpdated =
    data.lastUpdated != null
      ? new Date(data.lastUpdated).toLocaleTimeString("ru-RU")
      : "—";

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Общий объем */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Общий объем</h3>
          <span className="text-blue-500">📊</span>
        </div>
        <div className="text-2xl font-bold text-gray-900">{data.totalVolume}</div>
        <p className="text-xs text-gray-500">заказов за 24ч</p>
      </div>

      {/* Общая стоимость */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Общая стоимость</h3>
          <span className="text-green-500">💰</span>
        </div>
        <div className="text-2xl font-bold text-gray-900">{formatCurrency(totalValue)}</div>
        <p className="text-xs text-gray-500">оборот за 24ч</p>
      </div>

      {/* Растущие позиции */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Растущие позиции</h3>
          <span className="text-green-500">📈</span>
        </div>
        <div className="text-2xl font-bold text-green-600">{gainers}</div>
        <p className="text-xs text-gray-500">из {data.items.length} блюд</p>
      </div>

      {/* Падающие позиции */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-600">Падающие позиции</h3>
          <span className="text-red-500">📉</span>
        </div>
        <div className="text-2xl font-bold text-red-600">{losers}</div>
        <p className="text-xs text-gray-500">из {data.items.length} блюд</p>
      </div>

      {/* Сводка рынка */}
      <div className="bg-white rounded-lg shadow-md p-6 md:col-span-2 lg:col-span-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Сводка рынка</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{gainers}</div>
            <p className="text-sm text-gray-500">Растут</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">{losers}</div>
            <p className="text-sm text-gray-500">Падают</p>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-600">{stable}</div>
            <p className="text-sm text-gray-500">Стабильны</p>
          </div>
          <div className="text-center">
            <div className={`text-2xl font-bold ${avgPriceChange >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatPercentage(avgPriceChange)}
            </div>
            <p className="text-sm text-gray-500">Средний рост</p>
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
          <div className="flex items-center gap-1">
            <span>🕒</span>
            <span>Обновлено: {formattedLastUpdated}</span>
          </div>
          <div className={`flex items-center gap-1 font-medium ${
            data.marketTrend === "up" 
              ? "text-green-600" 
              : data.marketTrend === "down" 
              ? "text-red-600" 
              : "text-gray-600"
          }`}>
            {data.marketTrend === "up" && <span>📈</span>}
            {data.marketTrend === "down" && <span>📉</span>}
            {data.marketTrend === "stable" && <span>➡️</span>}
            Тренд: {data.marketTrend === "up" ? "Рост" : data.marketTrend === "down" ? "Падение" : "Стабильно"}
          </div>
        </div>
      </div>
    </div>
  );
}