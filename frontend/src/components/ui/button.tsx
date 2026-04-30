import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "../../lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "icon";
  children: ReactNode;
};

export function Button({ className, variant = "secondary", size = "md", children, ...props }: ButtonProps) {
  return (
    <button className={cx("button", `button--${variant}`, `button--${size}`, className)} {...props}>
      {children}
    </button>
  );
}
