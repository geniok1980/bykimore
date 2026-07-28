"use client";

import { BeerExchangeItem } from "@/types/beer-exchange";
import { useState, useEffect, useRef } from "react";

interface BeerExchangeTableProps {
  items: BeerExchangeItem[];
}

export default function BeerExchangeTable({ items }: BeerExchangeTableProps) {
  const [previousPrices, setPreviousPrices] = useState<Record<string, number>>({});
  const [blinkingItems, setBlinkingItems] = useState<Set<string>>(new Set());
  const timeoutRefs = useRef<Record<string, NodeJS.Timeout>>({});

  // Отслеживаем изменения цен и запускаем анимацию подмигивания
  useEffect(() => {
    const newBlinkingItems = new Set<string>();

    items.forEach(item => {
      const previousPrice = previousPrices[item.id];
      if (previousPrice !== undefined && previousPrice !== item.currentPrice) {
        newBlinkingItems.add(item.id);
        
        // Устанавливаем таймаут для удаления подмигивания через 2 секунды
        if (timeoutRefs.current[item.id]) {
          clearTimeout(timeoutRefs.current[item.id]);
        }
        
        timeoutRefs.current[item.id] = setTimeout(() => {
          setBlinkingItems(prev => {
            const newSet = new Set(prev);
            newSet.delete(item.id);
            return newSet;
          });
          delete timeoutRefs.current[item.id];
        }, 2000);
      }
    });

    if (newBlinkingItems.size > 0) {
      setBlinkingItems(prev => new Set([...prev, ...newBlinkingItems]));
    }

    // Обновляем предыдущие цены
    const newPreviousPrices: Record<string, number> = {};
    items.forEach(item => {
      newPreviousPrices[item.id] = item.currentPrice;
    });
    setPreviousPrices(newPreviousPrices);
  }, [items]);

  // Очищаем таймауты при размонтировании компонента
  useEffect(() => {
    return () => {
      Object.values(timeoutRefs.current).forEach(timeout => {
        clearTimeout(timeout);
      });
    };
  }, []);
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ru-RU", {
      style: "currency",
      currency: "RUB",
      minimumFractionDigits: 0,
    }).format(price);
  };

  const formatPriceChange = (percentage: number) => {
    if (percentage > 0) {
      return { symbol: "▲", color: "green", text: `+${percentage.toFixed(1)}%` };
    } else if (percentage < 0) {
      return { symbol: "▼", color: "red", text: `${percentage.toFixed(1)}%` };
    } else {
      return { symbol: "●", color: "gray", text: "0.0%" };
    }
  };

  return (
    <div className="tv-table-container">
      <div className="tv-table-wrapper">
        <table className="tv-table">
          <thead>
            <tr className="tv-table-header-row">
              <th className="tv-table-th dish-column">Блюдо</th>
              <th className="tv-table-th price-column">Цена</th>
              <th className="tv-table-th rate-column">Курс</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr 
                key={item.id} 
                className={`tv-table-row ${index % 2 === 0 ? 'even' : 'odd'} ${blinkingItems.has(item.id) ? 'price-changed' : ''}`}
              >
                <td className="tv-table-td dish-cell">
                  <div className="dish-info one-line">
                    <span className="dish-emoji">{item.image}</span>
                    <span className="dish-text">{item.name}</span>
                  </div>
                </td>
                <td className="tv-table-td price-cell">
                  <div className="price-info compact">
                    {item.stoplisted ? (
                      <span className="soldout-badge">РАСПРОДАНО</span>
                    ) : (
                      <span className="current-price">{formatPrice(item.currentPrice)}</span>
                    )}
                  </div>
                </td>
                <td className="tv-table-td rate-cell">
                  {item.stoplisted ? (
                    <div className="rate-badge compact">
                      <span className="rate-value hidden-rate">&nbsp;</span>
                    </div>
                  ) : (
                    <div className="rate-badge compact">
                      <span 
                        className="rate-triangle" 
                        style={{ color: formatPriceChange(item.priceChangePercentage24h).color }}
                      >
                        {formatPriceChange(item.priceChangePercentage24h).symbol}
                      </span>
                      <span className="rate-value">
                        {formatPriceChange(item.priceChangePercentage24h).text}
                      </span>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}