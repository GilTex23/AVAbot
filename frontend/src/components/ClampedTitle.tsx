import { useState } from "react";
import { cx } from "../lib/utils";

type ClampedTitleProps = {
  title: string;
  className?: string;
};

/** Длинное название — в несколько строк с многоточием; нажатие показывает его целиком */
export function ClampedTitle({ title, className }: ClampedTitleProps) {
  const [expanded, setExpanded] = useState(false);
  return (
    <h2
      className={cx("clamped-title", expanded && "clamped-title--expanded", className)}
      title={title}
      onClick={() => setExpanded((value) => !value)}
    >
      {title}
    </h2>
  );
}
