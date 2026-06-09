"use client";

import { ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { Badge } from "./ui/badge";
import { Card, CardContent } from "./ui/card";
import { cn } from "../lib/utils";

type MetricVariant = "default" | "elevated" | "severe";

type OperatorMetricCardProps = {
  badge?: string;
  badgeVariant?: MetricVariant;
  className?: string;
  detail?: ReactNode;
  label: string;
  onClick?: () => void;
  subtitle: string;
  tone?: MetricVariant;
  value: string;
  valueSuffix?: string;
  withColorBar?: boolean;
};

const badgeVariantMap: Record<MetricVariant, "outline" | "elevated" | "severe"> = {
  default: "outline",
  elevated: "elevated",
  severe: "severe"
};

const valueToneMap: Record<MetricVariant, string> = {
  default: "text-slate-900",
  elevated: "text-orange-700",
  severe: "text-red-700"
};

export function OperatorMetricCard({
  badge,
  badgeVariant = "default",
  className,
  detail,
  label,
  onClick,
  subtitle,
  tone = "default",
  value,
  valueSuffix,
  withColorBar = false
}: OperatorMetricCardProps) {
  return (
    <Card
      className={cn(
        "cursor-pointer border-slate-200 transition duration-150 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md",
        onClick ? "focus-within:ring-2 focus-within:ring-ring" : "cursor-default",
        className
      )}
      onClick={onClick}
      onKeyDown={(event) => {
        if (!onClick) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <CardContent className="space-y-3 p-4">
        <div className="space-y-2">
          <div className="flex min-h-[24px] items-start justify-start gap-2">
            {badge ? <Badge className="whitespace-nowrap self-start" variant={badgeVariantMap[badgeVariant]}>{badge}</Badge> : null}
            {onClick ? <ChevronRight className="mt-1 h-4 w-4 shrink-0 self-start text-slate-400" /> : null}
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-[11px] leading-4 text-slate-500">{subtitle}</div>
          </div>
        </div>

        <div className="flex items-end gap-1">
          <div className={cn("text-3xl font-semibold leading-none xl:text-[2rem]", valueToneMap[tone])}>{value}</div>
          {valueSuffix ? <div className="pb-1 text-xs text-slate-500">{valueSuffix}</div> : null}
        </div>

        {withColorBar ? (
          <div className="space-y-1">
            <div className="h-2 rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-red-800" />
            <div className="flex justify-between text-[10px] uppercase tracking-wide text-slate-400">
              <span>Low</span>
              <span>High</span>
            </div>
          </div>
        ) : null}

        {detail ? <div className="rounded-md bg-slate-50 px-3 py-2 text-[11px] leading-4 text-slate-600">{detail}</div> : null}
      </CardContent>
    </Card>
  );
}
