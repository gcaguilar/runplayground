import {
  Activity,
  Bike,
  Dumbbell,
  Footprints,
  Mountain,
  Waves,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

export function sportGlyph(sport: string | null | undefined): {
  icon: LucideIcon;
  tone: string;
} {
  const value = (sport ?? "").toLowerCase();
  if (value.includes("run")) return { icon: Footprints, tone: "lime" };
  if (value.includes("cycl") || value.includes("bike")) return { icon: Bike, tone: "blue" };
  if (value.includes("hik") || value.includes("trail")) return { icon: Mountain, tone: "amber" };
  if (value.includes("swim")) return { icon: Waves, tone: "cyan" };
  if (value.includes("strength")) return { icon: Dumbbell, tone: "violet" };
  if (value.includes("walk")) return { icon: Footprints, tone: "amber" };
  return { icon: Activity, tone: "neutral" };
}

export function SportGlyph({
  sport,
  size = "md",
  className,
}: {
  sport: string | null | undefined;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const { icon: Icon, tone } = sportGlyph(sport);
  return (
    <span className={cn("sport-glyph", `sport-glyph--${tone}`, `sport-glyph--${size}`, className)}>
      <Icon size={size === "lg" ? 24 : size === "sm" ? 14 : 18} aria-hidden="true" />
    </span>
  );
}
