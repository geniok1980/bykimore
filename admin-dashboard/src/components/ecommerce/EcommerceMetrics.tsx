"use client";
import React, { useEffect, useState } from "react";
import CurrentRevenueCard from "./CurrentRevenueCard";
import Badge from "../ui/badge/Badge";
import { BoxIconLine } from "@/icons";
import { listBeerExchangeSettings } from "@/lib/api";

export const EcommerceMetrics = () => {
  const [ordersTotal, setOrdersTotal] = useState<number | null>(null);
  const [ordersError, setOrdersError] = useState<string | null>(null);
  const [trendPct, setTrendPct] = useState<number | null>(null);
  const [trendDir, setTrendDir] = useState<"up" | "down" | "flat" | null>(null);

  // «Заказы» считаем как суммарное количество продаж (sales_quantity) по всем блюдам
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setOrdersError(null);
        const settings = await listBeerExchangeSettings();
        const total = settings.reduce((acc, s) => acc + (Number(s.sales_quantity ?? 0) || 0), 0);
        if (mounted) {
          setOrdersTotal(total);
          // Сравнение с прошлым периодом: используем сохранённое значение как базу
          const prevRaw = typeof window !== "undefined" ? localStorage.getItem("orders_total_prev") : null;
          const prev = prevRaw ? Number(prevRaw) : null;
          if (prev !== null && isFinite(prev) && prev > 0) {
            const diff = total - prev;
            const pct = (diff / prev) * 100;
            setTrendPct(pct);
            setTrendDir(diff > 0 ? "up" : diff < 0 ? "down" : "flat");
          } else {
            setTrendPct(null);
            setTrendDir(null);
          }
          // Обновляем базу для следующего сравнения
          try { localStorage.setItem("orders_total_prev", String(total)); } catch {}
        }
      } catch (e: any) {
        if (mounted) setOrdersError(e?.message || "Не удалось загрузить продажи");
      }
    })();
    return () => { mounted = false; };
  }, []);
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:gap-6">
      {/* Карточка «Текущая выручка» */}
      <CurrentRevenueCard />

      {/* Карточка «Заказы» */}
      <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] md:p-6">
        <div className="flex items-center justify-center w-12 h-12 bg-gray-100 rounded-xl dark:bg-gray-800">
          <BoxIconLine className="text-gray-800 dark:text-white/90" />
        </div>
        <div className="flex items-end justify-between mt-5">
          <div>
            <span className="text-sm text-gray-500 dark:text-gray-400">Заказы</span>
            <h4 className="mt-2 font-bold text-gray-800 text-title-sm dark:text-white/90">
              {ordersError ? (
                <span className="text-red-600 text-sm">Ошибка</span>
              ) : ordersTotal === null ? (
                <span className="text-gray-500">…</span>
              ) : (
                new Intl.NumberFormat("ru-RU").format(Math.round(ordersTotal))
              )}
            </h4>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Суммарное количество продаж по меню</p>
          </div>
          {/* Бейдж тренда: сравнение с прошлым сохранённым значением */}
          {trendPct !== null && trendDir !== null ? (
            <Badge color={trendDir === "up" ? "success" : trendDir === "down" ? "error" : "light"}>
              <span className={trendDir === "up" ? "text-success-500" : trendDir === "down" ? "text-error-500" : "text-gray-500"}>
                {trendDir === "up" ? "▲" : trendDir === "down" ? "▼" : "—"}
              </span>
              {Math.abs(trendPct).toFixed(1)}%
            </Badge>
          ) : (
            <Badge color="light">—</Badge>
          )}
        </div>
      </div>
    </div>
  );
};