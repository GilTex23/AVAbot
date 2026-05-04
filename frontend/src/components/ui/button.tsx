import type { ButtonHTMLAttributes, ReactNode } from "react";
import { hapticImpact } from "../../lib/telegram";
import { cx } from "../../lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "icon";
  children: ReactNode;
};

export function Button({ className, variant = "secondary", size = "md", children, onClick, disabled, ...props }: ButtonProps) {
  return (
    <button
      className={cx("button", `button--${variant}`, `button--${size}`, className)}
      disabled={disabled}
      onClick={(event) => {
        if (!disabled) {
          hapticImpact(variant === "danger" ? "medium" : "light");
        }
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </button>
  );
}
