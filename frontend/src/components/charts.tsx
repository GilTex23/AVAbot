import { Maximize2, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { hapticImpact, showTelegramBackButton } from "../lib/telegram";

/** Цвета рядов: различимы на тёмном фоне, первые — фирменный красный и зелёный */
export const CHART_COLORS = ["#ff5c57", "#25c94a", "#4ea1ff", "#f5b942", "#b07cff", "#2dd4bf", "#ff8fb1", "#a5a8ac"];

export type ChartSeries = {
  key: string;
  label: string;
  color: string;
  values: Array<number | null>;
};

export type LinePoint = {
  /** Позиция по оси X (индекс дня или время в мс) */
  x: number;
  label: string;
  value: number | null;
};

export type ChartMode = {
  height: number;
  full: boolean;
};

const PAD = { top: 10, right: 10, bottom: 22, left: 42 };
const numberFormat = new Intl.NumberFormat("ru-RU");
const compactFormat = new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 });

export function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : numberFormat.format(value);
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    setWidth(element.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function niceMax(value: number) {
  if (value <= 0) {
    return 1;
  }
  const power = 10 ** Math.floor(Math.log10(value));
  const scaled = value / power;
  return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * power;
}

/** X касания в координатах SVG — работает и когда график повёрнут на весь экран */
function pointerX(event: PointerEvent<SVGSVGElement>) {
  const svg = event.currentTarget;
  const matrix = svg.getScreenCTM();
  if (matrix) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(matrix.inverse()).x;
  }
  return event.clientX - svg.getBoundingClientRect().left;
}

function useScrub(count: number, toIndex: (x: number) => number) {
  const [selected, setSelected] = useState<number | null>(null);
  const pick = (event: PointerEvent<SVGSVGElement>) => {
    if (!count) {
      return;
    }
    const index = Math.min(count - 1, Math.max(0, toIndex(pointerX(event))));
    setSelected((current) => {
      if (current !== index) {
        hapticImpact("light");
      }
      return index;
    });
  };
  return {
    selected: selected === null || selected >= count ? count - 1 : selected,
    handlers: {
      onPointerDown: pick,
      onPointerMove: (event: PointerEvent<SVGSVGElement>) => {
        if (event.buttons || event.pointerType === "touch") {
          pick(event);
        }
      },
    },
  };
}

function YAxis({ max, width, innerHeight, format }: { max: number; width: number; innerHeight: number; format: (value: number) => string }) {
  return (
    <g>
      {[0, 0.5, 1].map((share) => {
        const y = PAD.top + innerHeight - share * innerHeight;
        return (
          <g key={share}>
            <line className="chart-grid" x1={PAD.left} x2={width - PAD.right} y1={y} y2={y} />
            <text className="chart-axis" x={PAD.left - 6} y={y + 4} textAnchor="end">
              {format(max * share)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function XLabels({ labels, positions, width, height }: { labels: string[]; positions: number[]; width: number; height: number }) {
  const count = labels.length;
  const innerWidth = Math.max(1, width - PAD.left - PAD.right);
  // Подпись примерно на каждые 64 px; последняя всегда видна, соседние не наезжают
  const step = Math.max(1, Math.ceil(count / Math.max(1, Math.floor(innerWidth / 64))));
  const indices: number[] = [];
  for (let index = 0; index < count; index += step) {
    indices.push(index);
  }
  if (count > 1 && indices[indices.length - 1] !== count - 1) {
    if (count - 1 - indices[indices.length - 1] < step / 2) {
      indices.pop();
    }
    indices.push(count - 1);
  }
  return (
    <g>
      {indices.map((index) => {
        const anchor = count > 1 && index === 0 ? "start" : count > 1 && index === count - 1 ? "end" : "middle";
        return (
          <text key={index} className="chart-axis" x={positions[index]} y={height - 6} textAnchor={anchor}>
            {labels[index]}
          </text>
        );
      })}
    </g>
  );
}

type BarChartProps = {
  labels: string[];
  series: ChartSeries[];
  mode: ChartMode;
  formatValue?: (value: number) => string;
  /** false — показывать в подписи только общий итог дня */
  breakdown?: boolean;
  /** false — ряды нельзя складывать по смыслу (отправлено и отложено), итог дня не показываем */
  showTotal?: boolean;
};

/** Столбцы по дням; несколько рядов складываются друг на друга */
export function BarChart({ labels, series, mode, formatValue = formatNumber, breakdown = true, showTotal = true }: BarChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const count = labels.length;
  const innerWidth = Math.max(0, width - PAD.left - PAD.right);
  const innerHeight = mode.height - PAD.top - PAD.bottom;
  const band = count ? innerWidth / count : 0;
  const barWidth = Math.max(1, Math.min(band * 0.72, 28));
  const totals = labels.map((_, index) => series.reduce((sum, item) => sum + (item.values[index] ?? 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const { selected, handlers } = useScrub(count, (x) => Math.floor((x - PAD.left) / (band || 1)));
  const centers = labels.map((_, index) => PAD.left + band * index + band / 2);
  const y = (value: number) => PAD.top + innerHeight - (value / max) * innerHeight;

  return (
    <div className="chart">
      <div ref={ref} className="chart__canvas">
        {width > 0 ? (
          <svg width={width} height={mode.height} className={mode.full ? "chart-svg chart-svg--full" : "chart-svg"} {...handlers}>
            <YAxis max={max} width={width} innerHeight={innerHeight} format={(value) => compactFormat.format(value)} />
            {count ? <rect className="chart-selection" x={PAD.left + band * selected} y={PAD.top} width={band} height={innerHeight} /> : null}
            {labels.map((_, index) => {
              let base = 0;
              return (
                <g key={index}>
                  {series.map((item) => {
                    const value = item.values[index] ?? 0;
                    if (value <= 0) {
                      return null;
                    }
                    const top = y(base + value);
                    const bottom = y(base);
                    base += value;
                    return <rect key={item.key} x={centers[index] - barWidth / 2} y={top} width={barWidth} height={Math.max(1, bottom - top)} fill={item.color} rx={Math.min(2, barWidth / 3)} />;
                  })}
                </g>
              );
            })}
            <XLabels labels={labels} positions={centers} width={width} height={mode.height} />
          </svg>
        ) : null}
      </div>
      {count ? (
        <p className="chart__caption">
          <b>{labels[selected]}</b>
          {breakdown && series.length > 1
            ? series
                .filter((item) => (item.values[selected] ?? 0) > 0)
                .map((item) => (
                  <span key={item.key}>
                    <i style={{ background: item.color }} />
                    {item.label}: {formatValue(item.values[selected] ?? 0)}
                  </span>
                ))
            : null}
          {showTotal || series.length === 1 ? (
            <span>
              {series.length > 1 && breakdown ? "всего" : series[0]?.label}: {formatValue(totals[selected])}
            </span>
          ) : totals[selected] === 0 ? (
            <span>нет событий</span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

type LineChartProps = {
  points: LinePoint[];
  color: string;
  label: string;
  mode: ChartMode;
  formatValue?: (value: number) => string;
  formatAxis?: (value: number) => string;
  xLabels?: string[];
};

/** Линия с заливкой; пропуски (null) рвут линию */
export function LineChart({ points, color, label, mode, formatValue = formatNumber, formatAxis, xLabels }: LineChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const count = points.length;
  const innerWidth = Math.max(0, width - PAD.left - PAD.right);
  const innerHeight = mode.height - PAD.top - PAD.bottom;
  const minX = count ? points[0].x : 0;
  const maxX = count ? points[count - 1].x : 1;
  const spanX = maxX - minX || 1;
  const xOf = (x: number) => (count === 1 ? PAD.left + innerWidth / 2 : PAD.left + ((x - minX) / spanX) * innerWidth);
  const max = niceMax(Math.max(0, ...points.map((point) => point.value ?? 0)));
  const yOf = (value: number) => PAD.top + innerHeight - (value / max) * innerHeight;
  const positions = points.map((point) => xOf(point.x));
  const { selected, handlers } = useScrub(count, (x) => {
    let nearest = 0;
    positions.forEach((position, index) => {
      if (Math.abs(position - x) < Math.abs(positions[nearest] - x)) {
        nearest = index;
      }
    });
    return nearest;
  });

  const segments: LinePoint[][] = [];
  let current: LinePoint[] = [];
  for (const point of points) {
    if (point.value === null) {
      if (current.length) {
        segments.push(current);
      }
      current = [];
    } else {
      current.push(point);
    }
  }
  if (current.length) {
    segments.push(current);
  }
  const bottom = PAD.top + innerHeight;
  const selectedPoint = points[selected];

  return (
    <div className="chart">
      <div ref={ref} className="chart__canvas">
        {width > 0 ? (
          <svg width={width} height={mode.height} className={mode.full ? "chart-svg chart-svg--full" : "chart-svg"} {...handlers}>
            <YAxis max={max} width={width} innerHeight={innerHeight} format={formatAxis || ((value) => compactFormat.format(value))} />
            {segments.map((segment, index) => {
              const line = segment.map((point, pointIndex) => `${pointIndex ? "L" : "M"}${xOf(point.x)},${yOf(point.value ?? 0)}`).join(" ");
              const area = `${line} L${xOf(segment[segment.length - 1].x)},${bottom} L${xOf(segment[0].x)},${bottom} Z`;
              return (
                <g key={index}>
                  <path d={area} fill={color} opacity={0.14} />
                  <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
                  {segment.length === 1 ? <circle cx={xOf(segment[0].x)} cy={yOf(segment[0].value ?? 0)} r={3} fill={color} /> : null}
                </g>
              );
            })}
            {selectedPoint ? (
              <g>
                <line className="chart-cursor" x1={positions[selected]} x2={positions[selected]} y1={PAD.top} y2={bottom} />
                {selectedPoint.value !== null ? <circle cx={positions[selected]} cy={yOf(selectedPoint.value)} r={4} fill={color} stroke="#141515" strokeWidth={2} /> : null}
              </g>
            ) : null}
            <XLabels labels={xLabels || points.map((point) => point.label)} positions={positions} width={width} height={mode.height} />
          </svg>
        ) : null}
      </div>
      {selectedPoint ? (
        <p className="chart__caption">
          <b>{selectedPoint.label}</b>
          <span>
            {label}: {selectedPoint.value === null ? "нет данных" : formatValue(selectedPoint.value)}
          </span>
        </p>
      ) : null}
    </div>
  );
}

export function Legend({ items }: { items: Array<{ label: string; color: string }> }) {
  if (items.length < 2) {
    return null;
  }
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span key={item.label}>
          <i style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

function useWindowSize() {
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight });
  useEffect(() => {
    const update = () => setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);
  return size;
}

type ChartCardProps = {
  title: string;
  subtitle?: string;
  legend?: Array<{ label: string; color: string }>;
  empty?: string | null;
  children: (mode: ChartMode) => ReactNode;
};

/** Карточка графика; по кнопке — на весь экран, при вертикальном телефоне график поворачивается горизонтально */
export function ChartCard({ title, subtitle, legend = [], empty, children }: ChartCardProps) {
  const [full, setFull] = useState(false);
  const close = useCallback(() => setFull(false), []);

  return (
    <section className="card chart-card">
      <div className="chart-card__head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {!empty ? (
          <button type="button" className="chart-card__expand" aria-label="На весь экран" onClick={() => setFull(true)}>
            <Maximize2 size={17} />
          </button>
        ) : null}
      </div>
      {empty ? (
        <p className="muted-copy">{empty}</p>
      ) : (
        <>
          <Legend items={legend} />
          {children({ height: 170, full: false })}
        </>
      )}
      {full ? <FullscreenChart title={title} subtitle={subtitle} legend={legend} onClose={close} render={children} /> : null}
    </section>
  );
}

type FullscreenChartProps = {
  title: string;
  subtitle?: string;
  legend: Array<{ label: string; color: string }>;
  onClose: () => void;
  render: (mode: ChartMode) => ReactNode;
};

function FullscreenChart({ title, subtitle, legend, onClose, render }: FullscreenChartProps) {
  const viewport = useWindowSize();
  // Телефон держат вертикально — поворачиваем слой на 90°, чтобы график шёл вдоль длинной стороны экрана
  const rotated = viewport.height > viewport.width;
  const width = rotated ? viewport.height : viewport.width;
  const height = rotated ? viewport.width : viewport.height;
  const chartHeight = Math.max(140, height - (legend.length > 1 ? 150 : 124));

  useEffect(() => showTelegramBackButton(onClose), [onClose]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  return createPortal(
    <div
      className="chart-fullscreen"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={{
        width,
        height,
        transform: rotated ? `translate(${viewport.width}px, 0) rotate(90deg)` : undefined,
      }}
    >
      <div className="chart-fullscreen__head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <button type="button" className="chart-card__expand" aria-label="Закрыть" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <Legend items={legend} />
      {render({ height: chartHeight, full: true })}
    </div>,
    document.body,
  );
}

export function StatTile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "danger" | "warning" }) {
  return (
    <div className="stat-tile">
      <span>{label}</span>
      <strong className={tone ? `stat-tile__value--${tone}` : undefined}>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}

/** Горизонтальные полосы: топ тайтлов, озвучки, таблицы БД */
export function BarList({ items, format = formatNumber }: { items: Array<{ label: string; value: number; hint?: string }>; format?: (value: number) => string }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div key={item.label} className="bar-list__row">
          <div className="bar-list__text">
            <span>{item.label}</span>
            <b>{format(item.value)}</b>
          </div>
          <div className="bar-list__track">
            <i style={{ width: `${Math.max(2, (item.value / max) * 100)}%` }} />
          </div>
          {item.hint ? <small>{item.hint}</small> : null}
        </div>
      ))}
    </div>
  );
}

export function UsageMeter({ used, total, format }: { used: number; total: number; format: (value: number) => string }) {
  const percent = total ? Math.min(100, (used / total) * 100) : 0;
  return (
    <div className="usage-meter">
      <div className="key-meter">
        <span className={`key-meter__fill key-meter__fill--${percent > 90 ? "red" : percent > 75 ? "amber" : "green"}`} style={{ width: `${percent}%` }} />
      </div>
      <small>
        {format(used)} из {format(total)} · {Math.round(percent)}%
      </small>
    </div>
  );
}
