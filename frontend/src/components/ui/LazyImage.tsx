import { useState } from "react";
import { ImageIcon } from "lucide-react";
import { cx } from "../../lib/utils";

type LazyImageProps = {
  src?: string;
  alt: string;
  className?: string;
};

export function LazyImage({ src, alt, className }: LazyImageProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className={cx("lazy-image lazy-image--empty", className)} aria-label={alt}>
        <ImageIcon size={22} />
      </div>
    );
  }

  return <img className={cx("lazy-image", className)} src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
}
