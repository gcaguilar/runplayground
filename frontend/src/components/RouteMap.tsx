import { useMemo } from "react";
import { MapPinOff } from "lucide-react";

import type { StreamPoint } from "@/api/client";
import { useI18n } from "@/i18n";
import { EmptyState } from "@/components/ui";

const WIDTH = 840;
const HEIGHT = 440;
const PADDING = 34;

export function RouteMap({ points }: { points: StreamPoint[] }) {
  const { t } = useI18n();

  const geometry = useMemo(() => {
    const usable = points.filter(
      (point) =>
        point.latitude !== null &&
        point.latitude !== undefined &&
        point.longitude !== null &&
        point.longitude !== undefined,
    );
    if (usable.length < 2) return null;

    const meanLatitude =
      usable.reduce((sum, point) => sum + (point.latitude ?? 0), 0) / usable.length;
    const cosLatitude = Math.cos((meanLatitude * Math.PI) / 180) || 1;

    const raw = usable.map((point) => ({
      x: (point.longitude ?? 0) * 111_320 * cosLatitude,
      y: (point.latitude ?? 0) * 110_540,
    }));

    const xs = raw.map((point) => point.x);
    const ys = raw.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const spanX = maxX - minX;
    const spanY = maxY - minY;
    const scale = Math.min(
      (WIDTH - PADDING * 2) / Math.max(spanX, 1),
      (HEIGHT - PADDING * 2) / Math.max(spanY, 1),
    );

    const offsetX = (WIDTH - spanX * scale) / 2;
    const offsetY = (HEIGHT - spanY * scale) / 2;
    const projected = raw.map((point) => ({
      x: offsetX + (point.x - minX) * scale,
      y: HEIGHT - (offsetY + (point.y - minY) * scale),
    }));

    const path = projected
      .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
      .join(" ");
    return {
      path,
      start: projected[0],
      end: projected[projected.length - 1],
      count: usable.length,
    };
  }, [points]);

  if (!geometry) {
    return <EmptyState compact icon={MapPinOff} title={t("detail.route.noGps")} />;
  }

  return (
    <div className="route-map">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="route-map__svg"
        role="img"
        aria-label={t("detail.route.title")}
      >
        <defs>
          <pattern id="route-grid" width="42" height="42" patternUnits="userSpaceOnUse">
            <path
              d="M 42 0 L 0 0 0 42"
              fill="none"
              stroke="var(--line)"
              strokeWidth="1"
            />
          </pattern>
          <filter id="route-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="url(#route-grid)" />
        <path
          d={geometry.path}
          fill="none"
          stroke="rgb(var(--accent-rgb) / 0.18)"
          strokeWidth="11"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={geometry.path}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          filter="url(#route-glow)"
        />
        <circle cx={geometry.start.x} cy={geometry.start.y} r="8" fill="var(--surface)" stroke="var(--accent)" strokeWidth="3" />
        <circle cx={geometry.end.x} cy={geometry.end.y} r="8" fill="var(--accent)" stroke="var(--surface)" strokeWidth="3" />
      </svg>
      <div className="route-map__legend">
        <span>
          <i className="map-dot map-dot--start" aria-hidden="true" />
          {t("detail.route.start")}
        </span>
        <span>
          <i className="map-dot map-dot--finish" aria-hidden="true" />
          {t("detail.route.finish")}
        </span>
      </div>
    </div>
  );
}
