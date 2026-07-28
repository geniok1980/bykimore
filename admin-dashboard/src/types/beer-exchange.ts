export interface BeerExchangeItem {
  id: string;
  name: string;
  // Признак, что позиция находится в стоп-листе (распродано / недоступно)
  stoplisted?: boolean;
  description: string;
  currentPrice: number;
  priceChange24h: number;
  priceChangePercentage24h: number;
  volume24h: number;
  category: 'appetizer' | 'main' | 'dessert' | 'drink' | 'snack';
  image: string;
  availability: boolean;
  rating: number;
  preparationTime: number; // в минутах
}

export interface BeerExchangeData {
  items: BeerExchangeItem[];
  totalVolume: number;
  marketTrend: 'up' | 'down' | 'stable';
  // Используем number|null, чтобы избежать гидрационных расхождений при SSR.
  // На сервере и при первом клиентском рендере значение null выводит стабильный плейсхолдер,
  // а фактическое время обновляется на клиенте после монтирования.
  lastUpdated: number | null;
}

export interface BeerExchangeStats {
  totalItems: number;
  gainers: number;
  losers: number;
  avgPriceChange: number;
}