"use client";
import React from "react";
import { GroupIcon, ArrowDownIcon, ArrowUpIcon } from "@/icons";
import Badge from "../ui/badge/Badge";
import { listBeerExchangeSettings, listPrices } from "@/lib/api";

const formatRub = (v: number) => new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
}).format(v);

export default function CurrentRevenueCard() {
  const [currentRevenue, setCurrentRevenue] = React.useState<number>(0);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    async function loadRevenue() {
      try {
        setLoading(true);
        setError(null);
        const [settings, prices] = await Promise.all([
          listBeerExchangeSettings(),
          listPrices(),
        ]);
        const latestPriceByDish: Record<number, { value: number; ts: number }> = {};
        for (const p of prices) {
          const ts = Date.parse(p.created_at);
          const prev = latestPriceByDish[p.dish_id];
          if (!prev || ts > prev.ts) latestPriceByDish[p.dish_id] = { value: p.value, ts };
        }
        const total = settings.reduce((sum, s) => {
          const price = Number(latestPriceByDish[s.dish_id]?.value ?? s.base_price ?? 0) || 0;
          const qty = Number(s.sales_quantity ?? 0) || 0;
          return sum + price * qty;
        }, 0);
        setCurrentRevenue(total);
      } catch (e: any) {
        setError(e?.message || "Ошибка загрузки выручки");
      } finally {
        setLoading(false);
      }
    }
    loadRevenue();
  }, []);

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] md:p-6">
      <div className="flex items-center justify-center w-12 h-12 bg-gray-100 rounded-xl dark:bg-gray-800">
        <GroupIcon className="text-gray-800 size-6 dark:text-white/90" />
      </div>
      <div className="flex items-end justify-between mt-5">
        <div>
          <span className="text-sm text-gray-500 dark:text-gray-400">Текущая выручка</span>
          <h4 className="mt-2 font-bold text-gray-800 text-title-sm dark:text-white/90">
            {loading ? "…" : formatRub(Math.round(currentRevenue))}
          </h4>
        </div>
        {error ? (
          <Badge color="error">
            <ArrowDownIcon className="text-error-500" />
            Ошибка
          </Badge>
        ) : (
          <Badge color="success">
            <ArrowUpIcon />
          </Badge>
        )}
      </div>
    </div>
  );
}