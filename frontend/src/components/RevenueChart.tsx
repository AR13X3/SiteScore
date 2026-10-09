import { useEffect, useMemo, useState } from "react";
import { escapeHtml, money, moneyExact, shortMonth } from "../lib/format";
import { siteColor, token } from "../lib/theme";
import type { CandidateSite, SimulationResult } from "../lib/types";
import { type ChartOption, useECharts } from "./useECharts";

interface Props {
  result: SimulationResult;
  sites: CandidateSite[];
  dark: boolean;
}

const DIRECT_LABEL_LIMIT = 4; // past this, end labels collide; legend + tooltip carry identity
const LABEL_FONT = "12px Inter, system-ui, sans-serif";
const MAX_LABEL_PX = 180;

let ctx: CanvasRenderingContext2D | null = null;
function textWidth(s: string): number {
  ctx ??= document.createElement("canvas").getContext("2d");
  if (!ctx) return s.length * 7;
  ctx.font = LABEL_FONT;
  return ctx.measureText(s).width;
}

/** Shorten a label with an ellipsis until it fits; the legend and tooltip keep the full name. */
function fitLabel(s: string, maxPx: number): string {
  if (textWidth(s) <= maxPx) return s;
  let out = s;
  while (out.length > 1 && textWidth(`${out}…`) > maxPx) out = out.slice(0, -1);
  return `${out.trimEnd()}…`;
}

export function RevenueChart({ result, sites, dark }: Props) {
  const [width, setWidth] = useState(800);
  const option = useMemo<ChartOption>(() => {
    const slotOf = new Map(sites.map((s) => [s.id, s.slot]));
    const months = result.sites[0]?.months.map((m) => m.month) ?? [];
    const text = token("--text-secondary");
    const muted = token("--text-muted");
    const grid = token("--grid");
    const surface = token("--surface");
    const last = months.length - 1;
    // End labels only when they leave most of the width to the plot; otherwise the
    // legend and tooltip carry identity (narrow screens).
    const maxLabelPx = Math.min(MAX_LABEL_PX, width * 0.22);
    const labelEnds = result.sites.length <= DIRECT_LABEL_LIMIT && maxLabelPx >= 70;
    const endLabels = new Map(
      result.sites.map((s) => [s.site.label || s.site.id, fitLabel(s.site.label || s.site.id, maxLabelPx)]),
    );
    const rightPad = labelEnds ? Math.max(...[...endLabels.values()].map(textWidth)) + 28 : 16;
    const bandOf = new Map(result.uncertainty?.sites.map((u) => [u.site_id, u.revenue]) ?? []);
    const lineIds = new Set(result.sites.map((s) => s.site.id));

    return {
      animationDuration: 900,
      animationEasing: "cubicOut",
      textStyle: { fontFamily: "Inter, system-ui, sans-serif" },
      grid: { left: 8, right: rightPad, top: 44, bottom: 8, containLabel: true },
      legend: {
        top: 0,
        left: 0,
        data: result.sites.map((s) => s.site.label || s.site.id),
        icon: "path://M0,4 L16,4 L16,6 L0,6 Z",
        itemWidth: 16,
        itemHeight: 6,
        textStyle: { color: text, fontSize: 12 },
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: muted, width: 1 } },
        backgroundColor: token("--surface-raised"),
        borderColor: grid,
        textStyle: { color: token("--text-primary"), fontSize: 12 },
        formatter: (params: unknown) => {
          type Row = { seriesId: string; seriesName: string; value: number; color: string; dataIndex: number };
          const rows = (params as Row[])
            .filter((r) => lineIds.has(r.seriesId))
            .sort((a, b) => b.value - a.value);
          const head = `<div class="tt-head">${shortMonth(months[rows[0]?.dataIndex ?? 0])} · month ${(rows[0]?.dataIndex ?? 0) + 1}</div>`;
          const body = rows
            .map((r) => {
              const band = bandOf.get(r.seriesId);
              const range = band
                ? `<span class="tt-range">${money(band.p10[r.dataIndex])}–${money(band.p90[r.dataIndex])}</span>`
                : "";
              return (
                `<div class="tt-row"><span class="tt-key" style="background:${r.color}"></span>` +
                `<strong>${moneyExact(r.value)}</strong>${range}<span class="tt-name">${escapeHtml(r.seriesName)}</span></div>`
              );
            })
            .join("");
          return head + body;
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: months,
        axisLine: { lineStyle: { color: grid } },
        axisTick: { show: false },
        axisLabel: { color: muted, formatter: shortMonth, interval: 5, fontSize: 11 },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: muted, formatter: (v: number) => money(v), fontSize: 11 },
        splitLine: { lineStyle: { color: grid, width: 1 } },
      },
      series: [
        // P10-P90 bands: an invisible P10 baseline plus a stacked wash up to P90.
        ...result.sites.flatMap((s) => {
          const band = bandOf.get(s.site.id);
          if (!band) return [];
          const color = siteColor(slotOf.get(s.site.id) ?? 0, dark);
          const common = {
            type: "line", stack: `band-${s.site.id}`, smooth: 0.2, symbol: "none", silent: true,
            lineStyle: { opacity: 0 }, tooltip: { show: false }, z: 1,
          };
          return [
            { ...common, id: `${s.site.id}-p10`, data: band.p10.map(Math.round) },
            {
              ...common, id: `${s.site.id}-band`,
              data: band.p90.map((v, i) => Math.round(v - band.p10[i])),
              areaStyle: { color, opacity: dark ? 0.16 : 0.12 },
            },
          ];
        }),
        ...result.sites.map((s) => {
        const color = siteColor(slotOf.get(s.site.id) ?? 0, dark);
        return {
          type: "line",
          id: s.site.id,
          z: 3,
          name: s.site.label || s.site.id,
          data: s.months.map((m) => Math.round(m.revenue)),
          color,
          smooth: 0.2,
          lineStyle: { width: 2, cap: "round", join: "round" },
          symbol: "circle",
          showSymbol: true,
          symbolSize: (_: unknown, p: { dataIndex: number }) => (p.dataIndex === last ? 8 : 0),
          itemStyle: { color, borderColor: surface, borderWidth: 2 },
          emphasis: { focus: "series", lineStyle: { width: 2 } },
          endLabel: {
            show: labelEnds,
            color: text,
            fontSize: 12,
            distance: 8,
            formatter: (p: { seriesName: string }) => endLabels.get(p.seriesName) ?? p.seriesName,
          },
        };
        }),
      ],
    };
  }, [result, sites, dark, width]);

  const ref = useECharts(option);
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, [ref]);
  return <div ref={ref} className="chart" role="img" aria-label="Projected monthly revenue per site over 36 months" />;
}
