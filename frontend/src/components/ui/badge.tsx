import type { ReactNode } from "react";
import { cx } from "../../lib/utils";

type BadgeProps = {
  tone?: "green" | "red" | "muted" | "amber";
  children: ReactNode;
  className?: string;
};

export function Badge({ tone = "muted", children, className }: BadgeProps) {
  return <span className={cx("badge", `badge--${tone}`, className)}>{children}</span>;
}
