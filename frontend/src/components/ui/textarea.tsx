import type { TextareaHTMLAttributes } from "react";
import { cx } from "../../lib/utils";

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx("textarea", className)} {...props} />;
}
