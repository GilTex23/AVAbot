import type { ReactNode } from "react";
import { cx } from "../../lib/utils";

type CardProps = {
  children: ReactNode;
  className?: string;
};

export function Card({ children, className }: CardProps) {
  return <section className={cx("card", className)}>{children}</section>;
}
