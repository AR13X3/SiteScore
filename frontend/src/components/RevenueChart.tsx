import { useMemo } from "react";
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
  const option = useMemo<ChartOption>(() => {
    const slotOf = new Map(sites.map((s) => [s.id, s.slot]));
    const months = result.sites[0]?.months.map((m) => m.month) ?? [];
    const text = token("--text-secondary");
    const muted = token("--text-muted");
    const grid = token("--grid");
    const surface = token("--surface");
    const last = months.length - 1;
    const labelEnds = result.sites.length <= DIRECT_LABEL_LIMIT;
    const endLabels = new Map(
      result.sites.map((s) => [s.site.label || s.site.id, fitLabel(s.site.label || s.site.id, MAX_LABEL_PX)]),
    );
    const rightPad = labelEnds ? Math.max(...[...endLabels.values()].map(textWidth)) + 28 : 16;

    return {
      animationDuration: 900,
      animationEasing: "cubicOut",
      textStyle: { fontFamily: "Inter, system-ui, sans-serif" },
      grid: { left: 8, right: rightPad, top: 44, bottom: 8, containLabel: true },
      legend: {
        top: 0,
        left: 0,
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
          const rows = (params as { seriesName: string; value: number; color: string; dataIndex: number }[])
            .slice()
            .sort((a, b) => b.value - a.value);
          const head = `<div class="tt-head">${shortMonth(months[rows[0]?.dataIndex ?? 0])} · month ${(rows[0]?.dataIndex ?? 0) + 1}</div>`;
          const body = rows
            .map(
              (r) =>
                `<div class="tt-row"><span class="tt-key" style="background:${r.color}"></span>` +
                `<strong>${moneyExact(r.value)}</strong><span class="tt-name">${escapeHtml(r.seriesName)}</span></div>`,
            )
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
      series: result.sites.map((s) => {
        const color = siteColor(slotOf.get(s.site.id) ?? 0, dark);
        return {
          type: "line",
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
    };
  }, [result, sites, dark]);

  const ref = useECharts(option);
  return <div ref={ref} className="chart" role="img" aria-label="Projected monthly revenue per site over 36 months" />;
}
