"use client";

import { BeerExchangeItem } from "@/types/beer-exchange";

interface BeerExchangeCardProps {
  item: BeerExchangeItem;
}

export default function BeerExchangeCard({ item }: BeerExchangeCardProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency: "RUB",
      minimumFractionDigits: 0,
    }).format(price);
  };

  return (
    <div className="beer-exchange-card bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow duration-300 overflow-hidden">
      {/* Image */}
      <div className="relative h-48 bg-gradient-to-br from-amber-100 to-orange-200">
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-6xl">{item.image}</span>
        </div>
        {!item.availability && (
          <div className="absolute top-2 right-2 bg-red-500 text-white px-2 py-1 rounded text-xs font-semibold">
            Недоступно
          </div>
        )}
        <div className="absolute top-2 left-2">
          <span className="beer-category-badge">
            {item.category}
          </span>
        </div>
      </div>
      
      <div className="p-4">
        {/* Title */}
        <h3 className="font-bold text-lg text-gray-900 mb-2">{item.name}</h3>
        
        {/* Description */}
        <p className="text-sm text-gray-600 mb-3 line-clamp-2">{item.description}</p>
        
        {/* Price and change */}
        <div className="flex items-center justify-between mb-2">
          <div className="text-lg font-bold text-gray-900">
            {formatPrice(item.currentPrice)}
          </div>
          <div
            className={`text-sm font-semibold ${
              item.priceChangePercentage24h >= 0
                ? "price-positive"
                : "price-negative"
            }`}
          >
            {item.priceChangePercentage24h >= 0 ? "+" : ""}
            {item.priceChangePercentage24h.toFixed(2)}%
          </div>
        </div>

        {/* Rating */}
        <div className="flex items-center gap-1 mb-3">
          <span className="beer-rating-stars">
            {"★".repeat(Math.floor(item.rating))}
            {"☆".repeat(5 - Math.floor(item.rating))}
          </span>
          <span className="text-sm text-gray-600">({item.rating})</span>
        </div>

        {/* Additional info */}
        <div className="space-y-2 text-xs text-gray-500">
          <div className="flex items-center justify-between">
            <span>⏱️ Время приготовления:</span>
            <span className="font-medium">{item.preparationTime} мин</span>
          </div>
          
          <div className="flex items-center justify-between">
            <span>📊 Объем за 24ч:</span>
            <span className="font-medium">{item.volume24h} заказов</span>
          </div>
          
          <div className="flex items-center justify-between">
            <span>💰 Изменение цены:</span>
            <span className={`font-medium ${
              item.priceChange24h >= 0 ? "text-green-600" : "text-red-600"
            }`}>
              {formatPrice(item.priceChange24h)}
            </span>
          </div>
          
          <div className="flex items-center justify-between">
            <span>📈 Статус:</span>
            <span className={`font-medium px-2 py-1 rounded text-xs ${
              item.availability 
                ? "bg-green-100 text-green-800" 
                : "bg-red-100 text-red-800"
            }`}>
              {item.availability ? "В наличии" : "Недоступно"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}