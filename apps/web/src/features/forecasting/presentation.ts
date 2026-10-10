import type { ForecastPreview } from "./demo-client";

export function forecastDate(date: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));
}

/** Chart projection only: copy supplied values; never extrapolate or subtract. */
export function chartPoints(data: ForecastPreview) {
  return [
    ...data.history.map((point) => ({ date: point.date, historical_capacity: point.capacity, historical_demand: point.demand, forecast_capacity: null, forecast_demand: null, capacity_range: null, demand_range: null })),
    ...data.forecast.map((point) => ({ date: point.date, historical_capacity: null, historical_demand: null, forecast_capacity: point.capacity, forecast_demand: point.demand, capacity_range: [point.capacity_lower, point.capacity_upper], demand_range: [point.demand_lower, point.demand_upper] })),
  ];
}
