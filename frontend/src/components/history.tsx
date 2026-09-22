"use client";
import type { Overview } from "@/lib/types";

export function History({ data }: { data: Overview["history"] }) {
  const max = Math.max(3, ...data.flatMap((d) => [d.opened, d.resolved]));
  const point = (value: number, index: number) =>
    `${24 + index * (692 / Math.max(1, data.length - 1))},${155 - (value / max) * 120}`;
  const line = (key: "opened" | "resolved") => data.map((d, i) => point(d[key], i)).join(" ");
  return (
    <div className="history-chart">
      <svg
        viewBox="0 0 740 190"
        role="img"
        aria-label="Incidents opened and resolved per day over the last 14 days"
      >
        <defs>
          <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#b6ef63" stopOpacity=".18" />
            <stop offset="100%" stopColor="#b6ef63" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line
              x1="24"
              y1={35 + 40 * i}
              x2="716"
              y2={35 + 40 * i}
              stroke="#2b3035"
              strokeDasharray="3 5"
            />
            <text x="2" y={39 + 40 * i} fill="#939ba6" fontSize="9">
              {Math.round(max * (1 - i / 3))}
            </text>
          </g>
        ))}
        <polygon points={`24,155 ${line("opened")} 716,155`} fill="url(#chart-fill)" />
        <polyline
          points={line("resolved")}
          fill="none"
          stroke="#7b89af"
          strokeWidth="2"
          strokeDasharray="5 5"
        />
        <polyline
          points={line("opened")}
          fill="none"
          stroke="#b6ef63"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        {data.map((d, i) => (
          <circle
            key={d.date}
            cx={24 + i * (692 / Math.max(1, data.length - 1))}
            cy={155 - (d.opened / max) * 120}
            r="3"
            fill="#b6ef63"
          >
            <title>
              {d.date}: {d.opened} opened, {d.resolved} resolved
            </title>
          </circle>
        ))}
        {data
          .filter((_, i) => i % 3 === 0 || i === data.length - 1)
          .map((d) => (
            <text
              key={d.date}
              x={24 + data.indexOf(d) * (692 / Math.max(1, data.length - 1))}
              y="180"
              textAnchor="middle"
              fill="#939ba6"
              fontSize="10"
            >
              {new Date(d.date + "T00:00:00").toLocaleDateString("en", {
                month: "short",
                day: "numeric",
              })}
            </text>
          ))}
      </svg>
    </div>
  );
}
