"use client";
import { useI18n } from "@/lib/i18n/context";

import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ForecastPreview } from "./demo-client";
import { chartPoints, forecastDate } from "./presentation";

export default function ForecastChart({ data }: { data: ForecastPreview }) {
  const { t, formatLocale } = useI18n();
  const first = data.forecast[0]?.date;
  const last = data.forecast.at(-1)?.date;
  return <div dir="ltr" className="h-[340px] w-full" role="group" aria-label={t("Historical and seven-day forecast capacity and demand, with uncalibrated uncertainty bands. Exact forecast values are in the table below.")}>
    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <ComposedChart data={chartPoints(data)} margin={{ top: 24, right: 22, left: 8, bottom: 12 }} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="date" tickFormatter={(date) => forecastDate(date, formatLocale)} tick={{ fontSize: 11 }} minTickGap={16} />
        <YAxis domain={[0, "auto"]} allowDecimals={false} tick={{ fontSize: 11 }} width={35} />
        <Tooltip labelFormatter={(value) => forecastDate(String(value), formatLocale)} formatter={(value) => t(Array.isArray(value) ? `${value.join("–")} places` : `${value ?? "Unknown"} places`)} />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 10 }} />
        {first && last && <ReferenceArea x1={first} x2={last} fill="#f0fdfa" fillOpacity={0.65} />}
        {first && <ReferenceLine x={first} stroke="#64748b" strokeDasharray="4 4" label={t({ value: t("Forecast"), position: "insideTopLeft", fill: "#475569", fontSize: 11 })} />}
        {data.first_gap && <ReferenceLine x={data.first_gap.date} stroke="#b45309" strokeDasharray="3 3" />}
        <Area type="linear" dataKey="capacity_range" name={t("Capacity range")} stroke="none" fill="#0f766e" fillOpacity={0.15} legendType="none" isAnimationActive={false} connectNulls={false} />
        <Area type="linear" dataKey="demand_range" name={t("Demand range")} stroke="none" fill="#b45309" fillOpacity={0.16} legendType="none" isAnimationActive={false} connectNulls={false} />
        <Line type="linear" dataKey="historical_capacity" name={t("Historical capacity")} stroke="#0f766e" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} connectNulls={false} />
        <Line type="linear" dataKey="historical_demand" name={t("Historical demand")} stroke="#b45309" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} connectNulls={false} />
        <Line type="linear" dataKey="forecast_capacity" name={t("Forecast capacity")} stroke="#0f766e" strokeDasharray="6 4" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} connectNulls={false} />
        <Line type="linear" dataKey="forecast_demand" name={t("Forecast demand")} stroke="#b45309" strokeDasharray="6 4" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} connectNulls={false} />
      </ComposedChart>
    </ResponsiveContainer>
  </div>;
}
