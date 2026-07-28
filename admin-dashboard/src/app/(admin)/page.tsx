import type { Metadata } from "next";
import { EcommerceMetrics } from "@/components/ecommerce/EcommerceMetrics";
import React from "react";
import MonthlySalesChart from "@/components/ecommerce/MonthlySalesChart";
import SalesQuantityChart from "@/components/ecommerce/SalesQuantityChart";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title:
    "Next.js E-commerce Dashboard | TailAdmin - Next.js Dashboard Template",
  description: "This is Next.js Home for TailAdmin Dashboard Template",
};

export default async function Ecommerce() {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;
  if (!token) {
    redirect("/signin");
  }
  return (
    <div className="grid grid-cols-12 gap-4 md:gap-6">
      <div className="col-span-12 space-y-6">
        {/* Оставляем только метрики: Текущая выручка и Заказы */}
        <EcommerceMetrics />

        {/* Оставляем диаграммы: Выручка по блюдам и Рейтинг по количеству продаж */}
        <MonthlySalesChart />
        <SalesQuantityChart />
      </div>
    </div>
  );
}
