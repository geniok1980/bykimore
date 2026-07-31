"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import "@/styles/bull-and-sea.css";
import { getBullAndSeaStats, BullAndSeaStats } from "@/lib/api.bull-and-sea";

export default function BullAndSeaPage() {
  const [stats, setStats] = useState<BullAndSeaStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Анимация при росте счётчика
  const prevPiecesRef = useRef<number | null>(null);
  const [bump, setBump] = useState(false);
  const [delta, setDelta] = useState(0);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await getBullAndSeaStats();
        setStats(data);
      } catch (e) {
        setError("Не удалось загрузить данные");
        console.error(e);
      }
    };
    fetchStats();
    // Обновляем каждые 30 секунд
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  // Следим за ростом счётчика и включаем анимацию
  useEffect(() => {
    if (stats?.total_pieces == null) return;
    const prev = prevPiecesRef.current;
    if (prev !== null && stats.total_pieces > prev) {
      setDelta(stats.total_pieces - prev);
      setBump(true);
    }
    prevPiecesRef.current = stats.total_pieces;
  }, [stats?.total_pieces]);

  useEffect(() => {
    if (!bump) return;
    const t = setTimeout(() => setBump(false), 1800);
    return () => clearTimeout(t);
  }, [bump]);

  const fmt = (n: number) => new Intl.NumberFormat("ru-RU").format(n);
  const fmtTons = (n: number) =>
    new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n);

  // Если данные ещё не загрузились — показываем прочерки
  const totalPieces = stats?.total_pieces ?? null;
  const totalTons = stats?.total_weight_kg ?? null;

  return (
    <div className="bs-root">
      {/* BACKDROP */}
      <div className="bs-backdrop" aria-hidden="true">
        <span className="bs-vignette" />
      </div>
      {/* HEADER */}
      <header className="bs-header">
        <div className="bs-header-left">
          <Image
            src="/images/logo-bull-and-sea.png"
            alt="Бык и Море"
            width={500}
            height={123}
            className="bs-logo-img"
            priority
          />
          <div className="bs-tagline">ЕДИМ БЫКА ЦЕЛИКОМ</div>
        </div>

        <div className="bs-header-right">
          <div className="bs-counter-head">СЧЁТЧИК СТЕЙКОВ</div>
          <div className="bs-counter-sub">
            <span className="bs-live-dot" aria-hidden="true" />
            Съедено за всю историю «Бык и Море»
          </div>
        </div>
      </header>

      {/* MAIN */}
      <main className="bs-main">
        <div className="bs-bull-col">
          <Image
            src="/images/bull.svg"
            alt=""
            aria-hidden="true"
            width={1212}
            height={823}
            className="bs-bull-img"
            priority
          />
        </div>

        <div className="bs-cards-col">
          <div className="bs-card">
            <div className="bs-card-body">
              <div className={`bs-card-num ${bump ? "bs-card-num-bump" : ""}`}>
                {totalPieces !== null ? fmt(totalPieces) : "—"}
              </div>
              {bump && delta > 0 && (
                <div className="bs-bump-badge" key={String(stats?.total_pieces)}>
                  +{fmt(delta)}
                </div>
              )}
            </div>
            <div className="bs-card-aside">
              <Image
                src="/images/decor-top.png"
                alt=""
                aria-hidden="true"
                width={410}
                height={330}
                className="bs-card-icon"
              />
              <div className="bs-card-unit">ШТУК</div>
            </div>
          </div>

          <div className="bs-sep" aria-hidden="true">
            <span className="bs-sep-line" />
            <span className="bs-sep-mark">✕</span>
            <span className="bs-sep-line" />
          </div>

          <div className="bs-card">
            <div className="bs-card-body">
              <div className="bs-card-label">ЭТО БОЛЕЕ</div>
              <div className="bs-card-num bs-card-num-sm">{totalTons !== null ? fmtTons(totalTons) : "—"}</div>
            </div>
            <div className="bs-card-aside">
              <Image
                src="/images/decor-bot.png"
                alt=""
                aria-hidden="true"
                width={385}
                height={340}
                className="bs-card-icon"
              />
              <div className="bs-card-unit">ТОНН</div>
            </div>
          </div>
        </div>
      </main>

      {/* FOOTER */}
      <footer className="bs-footer">
        <span className="bs-footer-text">
          ЕДИМ БЫКА ЦЕЛИКОМ <i className="bs-footer-dot" /> УВАЖАЕМ ПРИРОДУ{" "}
          <i className="bs-footer-dot" /> ПОДДЕРЖИВАЕМ ТРАДИЦИИ
        </span>
      </footer>
    </div>
  );
}
