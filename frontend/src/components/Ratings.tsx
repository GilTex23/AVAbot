import { Star } from "lucide-react";
import type { RatingItem } from "../lib/types";
import { cx, openAnime } from "../lib/utils";

const labels: Record<RatingItem["source"], string> = {
  animego: "AnimeGO",
  shikimori: "Shikimori",
  yummy: "Yummy",
};

const votesFormat = new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 });

export function formatRating(value: number) {
  return value.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

type RatingsProps = {
  items?: RatingItem[] | null;
  className?: string;
};

/** Оценки тайтла на сайтах: «★ 9,0 AnimeGO · 9,05 Shikimori»; нажатие открывает страницу тайтла на сайте */
export function Ratings({ items, className }: RatingsProps) {
  if (!items?.length) {
    return null;
  }
  return (
    <div className={cx("ratings", className)} aria-label="Оценки">
      <Star className="ratings__star" size={14} />
      {items.map((item) => (
        <button
          key={item.source}
          type="button"
          className="ratings__item"
          title={item.votes ? `${labels[item.source]}: ${formatRating(item.value)} (${item.votes.toLocaleString("ru-RU")} голосов)` : labels[item.source]}
          onClick={(event) => {
            event.stopPropagation();
            if (item.url) {
              openAnime(item.url);
            }
          }}
        >
          <strong>{formatRating(item.value)}</strong>
          <span>
            {labels[item.source]}
            {item.votes ? ` · ${votesFormat.format(item.votes)}` : ""}
          </span>
        </button>
      ))}
    </div>
  );
}
