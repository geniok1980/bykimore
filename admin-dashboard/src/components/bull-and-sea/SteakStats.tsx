"use client";

interface SteakData {
  label: string;
  pieces: number;
  tons: number;
}

interface SteakStatsProps {
  data: SteakData[];
}

export default function SteakStats({ data }: SteakStatsProps) {
  const formatNumber = (n: number) => {
    return new Intl.NumberFormat("ru-RU").format(n);
  };

  const formatTons = (n: number) => {
    return new Intl.NumberFormat("ru-RU", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  };

  return (
    <div className="bull-stats-container">
      <div className="bull-stats-header">
        <h2 className="bull-stats-title">В ресторане Бык и Море было съедено стейков</h2>
      </div>
      <div className="bull-stats-table-wrapper">
        <table className="bull-stats-table">
          <thead>
            <tr className="bull-stats-header-row">
              <th className="bull-stats-th bull-label-col">Позиция</th>
              <th className="bull-stats-th bull-pieces-col">Штук</th>
              <th className="bull-stats-th bull-tons-col">Тонн</th>
            </tr>
          </thead>
          <tbody>
            {data.map((item, index) => (
              <tr
                key={item.label}
                className={`bull-stats-row ${index % 2 === 0 ? "even" : "odd"}`}
              >
                <td className="bull-stats-td bull-label-cell">{item.label}</td>
                <td className="bull-stats-td bull-pieces-cell">{formatNumber(item.pieces)}</td>
                <td className="bull-stats-td bull-tons-cell">{formatTons(item.tons)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
