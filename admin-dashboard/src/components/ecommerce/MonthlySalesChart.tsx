"use client";
import { ApexOptions } from "apexcharts";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { getDishes, listBeerExchangeSettings, listPrices } from "@/lib/api";

// Динамический импорт ReactApexChart
const ReactApexChart = dynamic(() => import("react-apexcharts"), {
  ssr: false,
});

type RevenueItem = { name: string; revenue: number };

export default function MonthlySalesChart() {
  const [data, setData] = useState<RevenueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);
        const [dishes, settings, prices] = await Promise.all([
          getDishes(),
          listBeerExchangeSettings(),
          listPrices(),
        ]);

        const latestPriceByDish: Record<number, { value: number; ts: number }> = {};
        for (const p of prices) {
          const ts = Date.parse(p.created_at);
          const prev = latestPriceByDish[p.dish_id];
          if (!prev || ts > prev.ts) latestPriceByDish[p.dish_id] = { value: p.value, ts };
        }
        const settingsMap = new Map<number, { base_price?: number | null; sales_quantity?: number | null }>();
        for (const s of settings) {
          settingsMap.set(s.dish_id, { base_price: s.base_price, sales_quantity: s.sales_quantity });
        }
        const items: RevenueItem[] = dishes.map(dish => {
          const latest = latestPriceByDish[dish.id]?.value;
          const conf = settingsMap.get(dish.id);
          const price = Number(latest ?? conf?.base_price ?? 0) || 0;
          const qty = Number(conf?.sales_quantity ?? 0) || 0;
          const revenue = price * qty;
          return { name: dish.name, revenue };
        }).filter(i => i.revenue > 0);
        setData(items);
      } catch (e: any) {
        setError(e?.message || "Ошибка загрузки данных");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // Палитра для разного цвета каждого столбика
  const palette = [
    "#465FFF", "#FF4560", "#00E396", "#FEB019", "#775DD0",
    "#008FFB", "#00D9F9", "#A3A4A8", "#2E294E", "#D7263D",
    "#1B998B", "#F46036",
  ];
  const colors = palette.slice(0, Math.max(1, data.length));

  // Увеличиваем высоту диаграммы, особенно при большом количестве блюд
  // База 320px + небольшой бонус за каждые 10 элементов, максимум 560px
  const height = Math.min(560, 320 + Math.max(0, Math.ceil(data.length / 10) - 1) * 60);

  const options: ApexOptions = {
    colors,
    chart: {
      fontFamily: "Outfit, sans-serif",
      type: "bar",
      height,
      toolbar: { show: false },
    },
    plotOptions: { bar: { horizontal: false, columnWidth: "45%", borderRadius: 6, borderRadiusApplication: "end", distributed: true } },
    dataLabels: { enabled: false },
    stroke: { show: true, width: 4, colors: ["transparent"] },
    xaxis: {
      categories: data.map(d => d.name),
      axisBorder: { show: false },
      axisTicks: { show: false },
      // Чтобы подписи полностью умещались, отключаем тримминг и увеличиваем угол поворота
      labels: {
        rotate: -45,
        trim: false,
        style: { fontSize: "12px" },
      },
    },
    legend: { show: true, position: "top", horizontalAlign: "left", fontFamily: "Outfit" },
    yaxis: {
      title: { text: undefined },
      labels: { formatter: (val: number) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(val) },
    },
    grid: { yaxis: { lines: { show: true } } },
    tooltip: {
      x: { show: true },
      y: { formatter: (val: number) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(val) },
    },
  };
  const series = [{ name: "Выручка", data: data.map(d => Math.round(d.revenue)) }];

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white px-5 pt-5 dark:border-gray-800 dark:bg-white/[0.03] sm:px-6 sm:pt-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">Выручка по блюдам</h3>
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="max-w-full overflow-x-auto custom-scrollbar">
        <div className="-ml-5 min-w-[650px] xl:min-w-full pl-2">
          {loading ? (
            <div className="py-10 text-center text-gray-500 dark:text-gray-400">Загрузка…</div>
          ) : (
            <ReactApexChart options={options} series={series} type="bar" height={height} />
          )}
        </div>
      </div>
    </div>
  );
}