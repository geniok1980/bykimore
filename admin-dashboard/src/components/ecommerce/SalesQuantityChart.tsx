"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { getDishes, listBeerExchangeSettings } from "@/lib/api";

// Динамический импорт ReactApexChart
const ReactApexChart = dynamic(() => import("react-apexcharts"), {
  ssr: false,
});

type SalesItem = { name: string; qty: number };

export default function SalesQuantityChart() {
  const [data, setData] = useState<SalesItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);
        const [dishes, settings] = await Promise.all([
          getDishes(),
          listBeerExchangeSettings(),
        ]);

        const dishMap = new Map<number, string>(
          dishes.map((d) => [d.id, d.name])
        );

        const items: SalesItem[] = settings
          .map((s) => {
            const name = dishMap.get(s.dish_id) ?? `Блюдо ${s.dish_id}`;
            const qty = Number(s.sales_quantity ?? 0) || 0;
            return { name, qty };
          })
          .filter((i) => i.qty > 0)
          .sort((a, b) => b.qty - a.qty);

        setData(items);
      } catch (e: any) {
        setError(e?.message || "Ошибка загрузки данных");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const height = useMemo(() => {
    // Высота графика адаптируется под количество строк, но ограничена
    const base = 28 * Math.max(6, data.length);
    return Math.max(260, Math.min(460, base));
  }, [data.length]);

  // Палитра для разноцветных столбиков
  const palette = [
    "#465FFF", "#FF4560", "#00E396", "#FEB019", "#775DD0",
    "#008FFB", "#00D9F9", "#A3A4A8", "#2E294E", "#D7263D",
    "#1B998B", "#F46036",
  ];
  const colors = palette.slice(0, Math.max(1, data.length));

  const options: import("apexcharts").ApexOptions = {
    colors,
    chart: {
      fontFamily: "Outfit, sans-serif",
      type: "bar",
      toolbar: { show: false },
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 6,
        barHeight: "60%",
        distributed: true,
      },
    },
    dataLabels: { enabled: false },
    stroke: { show: true, width: 4, colors: ["transparent"] },
    xaxis: {
      categories: data.map((d) => d.name),
      title: { text: undefined },
      labels: {
        formatter: (val: string) => `${Math.round(Number(val))}`,
        style: { fontSize: "12px" },
      },
    },
    yaxis: {
      labels: {
        style: { fontSize: "12px" },
      },
    },
    grid: { yaxis: { lines: { show: true } } },
    tooltip: {
      x: { show: true },
      y: { formatter: (val: number) => `${Math.round(val)} шт.` },
    },
    legend: { show: true, position: "top", horizontalAlign: "left", fontFamily: "Outfit" },
  };

  const series = [
    {
      name: "Продажи",
      data: data.map((d) => Math.round(d.qty)),
    },
  ];

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white px-5 pt-5 dark:border-gray-800 dark:bg-white/[0.03] sm:px-6 sm:pt-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">Рейтинг по количеству продаж</h3>
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="max-w-full overflow-x-auto custom-scrollbar">
        <div className="-ml-5 xl:min-w-full pl-2">
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