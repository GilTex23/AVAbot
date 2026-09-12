import { ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { BarChart, BarList, CHART_COLORS, ChartCard, LineChart, StatTile, UsageMeter, formatNumber, type ChartSeries } from "../components/charts";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { ApiError, getAdminStats } from "../services/api";
import { showTelegramBackButton } from "../lib/telegram";
import { useTimeZone } from "../lib/timezones";
import type { AdminStats as AdminStatsData, DailySeries } from "../lib/types";

type AdminStatsProps = {
  refreshKey: number;
  onBack: () => void;
};

const PERIODS = [7, 30, 90, 180];
const NO_DATA = "Пока нет данных — статистика собирается с момента обновления бота.";

const SOURCE_LABELS: Record<string, string> = {
  checker: "Проверка новых серий",
  status_check: "Проверка подписок",
  miniapp: "Мини-апп",
  bot: "Бот",
  admin: "Админка",
  other: "Прочее",
};
const PAGE_LABELS: Record<string, string> = { home: "Главная", anime: "Страницы тайтлов" };
const FAILURE_LABELS: Record<string, string> = {
  "401": "401 · ключ недействителен",
  "403": "403 · кредиты кончились",
  "404": "404 · нет страницы",
  "429": "429 · слишком часто",
  "500": "500 · AnimeGO не ответил",
  timeout: "Таймаут",
  network: "Сеть",
};
const HOME_RESULTS: Record<string, { label: string; color: string }> = {
  ok: { label: "Успешно", color: "#25c94a" },
  timezone_unknown: { label: "Незнакомый пояс", color: "#f5b942" },
  problem: { label: "Проблема разметки", color: "#ff5c57" },
  fetch_failed: { label: "Не загрузилась", color: "#a5a8ac" },
};
const KEY_STATUS_LABELS: Record<string, string> = { invalid: "недействителен", exhausted: "исчерпан", low: "мало кредитов", active: "снова работает" };

const bytesUnits = ["Б", "КБ", "МБ", "ГБ", "ТБ"];

function formatBytes(bytes: number) {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < bytesUnits.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: value < 10 && unit ? 1 : 0 })} ${bytesUnits[unit]}`;
}

function formatDuration(seconds: number) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) {
    return `${days} д ${hours} ч`;
  }
  if (hours) {
    return `${hours} ч ${minutes} мин`;
  }
  return `${minutes} мин`;
}

function sum(values: Array<number | null>) {
  return values.reduce<number>((total, value) => total + (value ?? 0), 0);
}

function sumSeries(record: DailySeries) {
  return Object.values(record).reduce((total, values) => total + sum(values), 0);
}

function percent(part: number, total: number) {
  return total ? `${((part / total) * 100).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%` : "—";
}

function toSeries(record: DailySeries, labels: Record<string, string> = {}, colors: Record<string, string> = {}): ChartSeries[] {
  return Object.entries(record).map(([key, values], index) => ({
    key,
    label: labels[key] || key,
    color: colors[key] || CHART_COLORS[index % CHART_COLORS.length],
    values,
  }));
}

function legendOf(series: ChartSeries[]) {
  return series.map((item) => ({ label: item.label, color: item.color }));
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="stats-section">
      <div className="stats-section__head">
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function AdminStats({ refreshKey, onBack }: AdminStatsProps) {
  const timeZone = useTimeZone();
  const [period, setPeriod] = useState(30);
  const [data, setData] = useState<AdminStatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => showTelegramBackButton(onBack), [onBack]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    getAdminStats(period)
      .then((stats) => {
        if (!cancelled) {
          setData(stats);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(
            error instanceof ApiError && error.status === 401
              ? "Сессия Telegram устарела — закройте и снова откройте мини-апп."
              : "Не удалось загрузить статистику. Попробуйте ещё раз.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [period, refreshKey]);

  const labels = useMemo(
    () => (data?.days || []).map((day) => new Date(`${day}T00:00:00Z`).toLocaleDateString("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" })),
    [data],
  );

  return (
    <div className="page-stack">
      <section className="admin-title">
        <Button size="icon" variant="ghost" aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} />
        </Button>
        <div>
          <h1>Статистика</h1>
          <p>Запросы, ключи, бот, база данных и сервер</p>
        </div>
      </section>

      <div className="chip-row" role="tablist" aria-label="Период">
        {PERIODS.map((days) => (
          <button key={days} type="button" role="tab" aria-selected={period === days} className={period === days ? "chip chip--active" : "chip"} onClick={() => setPeriod(days)}>
            {days} дней
          </button>
        ))}
        {loading && data ? <Loader2 className="spin stats-loading" size={18} /> : null}
      </div>

      {notice ? <div className="notice">{notice}</div> : null}

      {loading && !data ? (
        <Card className="empty-state">
          <Loader2 className="spin" size={24} />
          Собираю статистику...
        </Card>
      ) : null}

      {data ? <StatsContent data={data} labels={labels} timeZone={timeZone} /> : null}
    </div>
  );
}

function StatsContent({ data, labels, timeZone }: { data: AdminStatsData; labels: string[]; timeZone: string }) {
  const { scraper, bot, history, database, server } = data;

  const successBySource = toSeries(scraper.success_by_source, SOURCE_LABELS);
  const successByPage = toSeries(scraper.success_by_page, PAGE_LABELS, { home: CHART_COLORS[2], anime: CHART_COLORS[4] });
  const byKey = toSeries(scraper.by_key);
  const failures = toSeries(scraper.failed_by_status, FAILURE_LABELS);
  const homeResults = toSeries(
    data.parser.home_results,
    Object.fromEntries(Object.entries(HOME_RESULTS).map(([key, value]) => [key, value.label])),
    Object.fromEntries(Object.entries(HOME_RESULTS).map(([key, value]) => [key, value.color])),
  );

  const successTotal = sumSeries(scraper.success_by_source);
  const failedTotal = sum(scraper.failed) + sum(scraper.timeouts);
  const requestsTotal = successTotal + failedTotal;
  const cacheTotal = sum(scraper.cache_hits);
  const latencyDays = scraper.latency_avg_ms.filter((value): value is number => value !== null);
  const latencyAvg = latencyDays.length ? latencyDays.reduce((total, value) => total + value, 0) / latencyDays.length : null;
  const statusChanges = Object.entries(scraper.key_status_changes)
    .map(([status, values]) => ({ status, count: sum(values) }))
    .filter((item) => item.count > 0);
  const lastCredits = scraper.credits[scraper.credits.length - 1];

  const creditPoints = scraper.credits.map((point) => ({
    x: new Date(point.at).getTime(),
    value: point.remaining,
    label: new Date(point.at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone }),
  }));
  const creditLabels = scraper.credits.map((point) => new Date(point.at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", timeZone }));
  const latencyPoints = scraper.latency_avg_ms.map((value, index) => ({ x: index, value: value === null ? null : value / 1000, label: labels[index] }));

  const notifications: ChartSeries[] = [
    { key: "sent", label: "Отправлено", color: CHART_COLORS[1], values: bot.notifications_sent },
    { key: "deferred", label: "Отложено тихими часами", color: CHART_COLORS[3], values: bot.notifications_deferred },
  ];
  const subscriptions: ChartSeries[] = [
    { key: "created", label: "Добавлено", color: CHART_COLORS[1], values: bot.subscriptions_created },
    { key: "deleted", label: "Удалено вручную", color: CHART_COLORS[7], values: bot.subscriptions_deleted },
    { key: "completed", label: "Завершено", color: CHART_COLORS[2], values: bot.subscriptions_completed },
    { key: "stale", label: "Брошенные озвучки", color: CHART_COLORS[3], values: bot.subscriptions_stale },
  ];

  return (
    <>
      <Section title="ScraperAPI" subtitle="Запросы к AnimeGO через прокси: кто их делает и сколько стоят">
        <div className="stat-tiles">
          <StatTile label="Запросов" value={formatNumber(requestsTotal)} hint={`${formatNumber(successTotal)} успешных`} />
          <StatTile label="Ошибок" value={percent(failedTotal, requestsTotal)} hint={`${formatNumber(failedTotal)} запросов`} tone={failedTotal > requestsTotal * 0.2 ? "danger" : undefined} />
          <StatTile label="Среднее время ответа" value={latencyAvg === null ? "—" : `${(latencyAvg / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`} />
          <StatTile label="Взято из кэша" value={formatNumber(cacheTotal)} hint="столько кредитов не потрачено" />
          <StatTile
            label="Кредитов в ротации"
            value={lastCredits ? formatNumber(lastCredits.remaining) : "—"}
            hint={lastCredits ? `из ${formatNumber(lastCredits.limit)}` : "появится после опроса ключей"}
          />
          <StatTile
            label="Смены статуса ключей"
            value={formatNumber(statusChanges.reduce((total, item) => total + item.count, 0))}
            hint={statusChanges.map((item) => `${KEY_STATUS_LABELS[item.status] || item.status}: ${item.count}`).join(", ") || "без происшествий"}
          />
        </div>

        <ChartCard title="Успешные запросы по источникам" subtitle="Каждый — минимум один кредит" legend={legendOf(successBySource)} empty={successTotal ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={successBySource} mode={mode} />}
        </ChartCard>
        <ChartCard title="Главная или страницы тайтлов" legend={legendOf(successByPage)} empty={successTotal ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={successByPage} mode={mode} />}
        </ChartCard>
        <ChartCard title="Запросы по ключам" legend={legendOf(byKey)} empty={sumSeries(scraper.by_key) ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={byKey} mode={mode} />}
        </ChartCard>
        <ChartCard title="Ошибки" subtitle="По ответу ScraperAPI" legend={legendOf(failures)} empty={failedTotal ? null : "Ошибок за период не было."}>
          {(mode) => <BarChart labels={labels} series={failures} mode={mode} />}
        </ChartCard>
        <ChartCard title="Время ответа" subtitle="Среднее за день, секунды" empty={latencyDays.length ? null : NO_DATA}>
          {(mode) => (
            <LineChart
              points={latencyPoints}
              color={CHART_COLORS[2]}
              label="В среднем"
              mode={mode}
              formatValue={(value) => `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`}
              formatAxis={(value) => `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`}
            />
          )}
        </ChartCard>
        <ChartCard title="Остаток кредитов" subtitle="Сумма по ключам в ротации, снимок раз в 6 часов" empty={creditPoints.length ? null : NO_DATA}>
          {(mode) => <LineChart points={creditPoints} xLabels={creditLabels} color={CHART_COLORS[1]} label="Осталось" mode={mode} />}
        </ChartCard>
        <ChartCard title="Взято из кэша" subtitle="Страница уже была загружена за последние 5 минут" empty={cacheTotal ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={[{ key: "cache", label: "Из кэша", color: CHART_COLORS[5], values: scraper.cache_hits }]} mode={mode} />}
        </ChartCard>
      </Section>

      <Section title="Парсер AnimeGO" subtitle="Результат каждой загрузки главной (раз в 15 минут)">
        <ChartCard title="Загрузки главной" legend={legendOf(homeResults)} empty={sumSeries(data.parser.home_results) ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={homeResults} mode={mode} />}
        </ChartCard>
      </Section>

      <Section title="Бот" subtitle="Пользователи, уведомления и подписки">
        <div className="stat-tiles">
          <StatTile label="Пользователей" value={formatNumber(bot.users)} hint={`${formatNumber(bot.subscribers)} с подписками`} />
          <StatTile label="Активных за 7 дней" value={formatNumber(bot.active_7d)} hint={`за 30 дней — ${formatNumber(bot.active_30d)}`} />
          <StatTile label="Подписок" value={formatNumber(bot.subscriptions)} hint={`тихие часы у ${formatNumber(bot.quiet_hours_users)}`} />
          <StatTile label="Уведомлений" value={formatNumber(sum(bot.notifications_sent))} hint="за период" />
        </div>

        <ChartCard title="Активные пользователи" subtitle="Заходили в мини-апп или писали боту" empty={sum(bot.active_total) ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={[{ key: "active", label: "Активных", color: CHART_COLORS[2], values: bot.active_total }]} mode={mode} />}
        </ChartCard>
        <ChartCard title="Новые пользователи" empty={sum(bot.new_users) ? null : "Новых пользователей за период не было."}>
          {(mode) => <BarChart labels={labels} series={[{ key: "new", label: "Новых", color: CHART_COLORS[4], values: bot.new_users }]} mode={mode} />}
        </ChartCard>
        <ChartCard title="Уведомления о сериях" legend={legendOf(notifications)} empty={sum(bot.notifications_sent) + sum(bot.notifications_deferred) ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={notifications} mode={mode} showTotal={false} />}
        </ChartCard>
        <ChartCard title="Подписки" legend={legendOf(subscriptions)} empty={subscriptions.some((item) => sum(item.values)) ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={subscriptions} mode={mode} showTotal={false} />}
        </ChartCard>

        {bot.top_titles.length ? (
          <Card className="chart-card">
            <h3 className="stats-card-title">Популярные тайтлы</h3>
            <BarList items={bot.top_titles.map((item) => ({ label: item.title, value: item.count }))} />
          </Card>
        ) : null}
        {bot.voiceovers.length ? (
          <Card className="chart-card">
            <h3 className="stats-card-title">Озвучки в подписках</h3>
            <BarList items={bot.voiceovers.map((item) => ({ label: item.name, value: item.count }))} />
          </Card>
        ) : null}
      </Section>

      <Section title="История для прогнозов" subtitle="Выходы серий из ленты и расписание оригинала">
        <div className="stat-tiles">
          <StatTile label="Выходов серий" value={formatNumber(history.releases)} hint={`${formatNumber(history.titles)} тайтлов`} />
          <StatTile label="Серий в расписании" value={formatNumber(history.airings)} />
        </div>
        <ChartCard title="Новые выходы серий" subtitle="Сколько серий в озвучках бот увидел за день" empty={sum(history.releases_per_day) ? null : NO_DATA}>
          {(mode) => <BarChart labels={labels} series={[{ key: "releases", label: "Выходов", color: CHART_COLORS[0], values: history.releases_per_day }]} mode={mode} />}
        </ChartCard>
      </Section>

      <Section title="База данных" subtitle={`PostgreSQL ${database.version} · статистика и история хранятся ${database.retention_days} дней`}>
        <div className="stat-tiles">
          <StatTile label="Размер базы" value={formatBytes(database.size_bytes)} />
          <StatTile label="Подключений" value={formatNumber(database.connections)} />
          <StatTile
            label="Работает"
            value={database.started_at ? formatDuration((Date.now() - new Date(database.started_at).getTime()) / 1000) : "—"}
            hint="с последнего запуска Postgres"
          />
        </div>
        <Card className="chart-card">
          <h3 className="stats-card-title">Таблицы</h3>
          <BarList
            format={formatBytes}
            items={database.tables.map((table) => ({
              label: table.name,
              value: table.total_bytes,
              hint: `${formatNumber(table.rows)} строк · данные ${formatBytes(table.table_bytes)} · индексы ${formatBytes(table.index_bytes)}`,
            }))}
          />
        </Card>
      </Section>

      <Section title="Сервер" subtitle="Контейнер бота">
        <div className="stat-tiles">
          <StatTile
            label="Процессор"
            value={`${Math.round(server.cpu_percent)}%`}
            hint={[server.cpu_count ? `${server.cpu_count} ядер` : null, server.load_average ? `нагрузка ${server.load_average.join(" / ")}` : null].filter(Boolean).join(" · ")}
            tone={server.cpu_percent > 85 ? "danger" : undefined}
          />
          <StatTile label="Память бота" value={formatBytes(server.process_memory)} hint={`Python ${server.python}`} />
          <StatTile label="Бот работает" value={formatDuration(server.process_uptime_seconds)} hint={`сервер — ${formatDuration(server.system_uptime_seconds)}`} />
          <StatTile label="Логи" value={formatBytes(server.logs_bytes)} />
        </div>
        <Card className="chart-card">
          <h3 className="stats-card-title">Память</h3>
          <UsageMeter used={server.memory_used} total={server.memory_total} format={formatBytes} />
          <h3 className="stats-card-title">Диск</h3>
          <UsageMeter used={server.disk_used} total={server.disk_total} format={formatBytes} />
        </Card>
      </Section>
    </>
  );
}
