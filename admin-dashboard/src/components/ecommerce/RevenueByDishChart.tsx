"use client";
import React from "react";
import dynamic from "next/dynamic";
import type { ApexOptions } from "apexcharts";
import { Dish, listBeerExchangeSettings, listPrices, getDishes } from "@/lib/api";

// Динамический импорт ReactApexChart
const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false });

type RevenueItem = { name: string; revenue: number };

export default function RevenueByDishChart() {
  const [data, setData] = React.useState<RevenueItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);
        const [dishes, settings, prices] = await Promise.all([
          getDishes(),
          listBeerExchangeSettings(),
          listPrices(),
        ]);

        // Карта последних цен по блюду
        const latestPriceByDish: Record<number, { value: number; ts: number }> = {};
        for (const p of prices) {
          const ts = Date.parse(p.created_at);
          const prev = latestPriceByDish[p.dish_id];
          if (!prev || ts > prev.ts) {
            latestPriceByDish[p.dish_id] = { value: p.value, ts };
          }
        }

        // Карта настроек по dish_id
        const settingsMap = new Map<number, { base_price?: number | null; sales_quantity?: number | null }>();
        for (const s of settings) {
          settingsMap.set(s.dish_id, { base_price: s.base_price, sales_quantity: s.sales_quantity });
        }

        // Сформировать данные: выручка = цена * количество продаж
        const items: RevenueItem[] = dishes.map((dish: Dish) => {
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

  const options: ApexOptions = {
    colors: ["#465FFF"],
    chart: {
      fontFamily: "Outfit, sans-serif",
      type: "bar",
      height: 240,
      toolbar: { show: false },
    },
    plotOptions: {
      bar: {
        horizontal: false,
        columnWidth: "45%",
        borderRadius: 6,
        borderRadiusApplication: "end",
      },
    },
    dataLabels: { enabled: false },
    stroke: { show: true, width: 4, colors: ["transparent"] },
    xaxis: {
      categories: data.map(d => d.name),
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { rotate: -15, trim: true },
    },
    legend: {
      show: true,
      position: "top",
      horizontalAlign: "left",
      fontFamily: "Outfit",
    },
    yaxis: {
      title: { text: undefined },
      labels: {
        formatter: (val: number) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(val),
      },
    },
    grid: { yaxis: { lines: { show: true } } },
    tooltip: {
      x: { show: true },
      y: {
        formatter: (val: number) => new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(val),
      },
    },
  };

  const series = [
    { name: "Выручка", data: data.map(d => Math.round(d.revenue)) },
  ];

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white px-5 pt-5 dark:border-gray-800 dark:bg-white/[0.03] sm:px-6 sm:pt-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">Выручка по блюдам</h3>
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-600">{error}</p>
      )}

      <div className="max-w-full overflow-x-auto custom-scrollbar">
        <div className="-ml-5 min-w-[650px] xl:min-w-full pl-2">
          {loading ? (
            <div className="py-10 text-center text-gray-500 dark:text-gray-400">Загрузка…</div>
          ) : (
            <ReactApexChart options={options} series={series} type="bar" height={240} />
          )}
        </div>
      </div>
    </div>
  );
}