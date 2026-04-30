const fallbackTimeZones = [
  "UTC",
  "Europe/Moscow",
  "Europe/Kaliningrad",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Omsk",
  "Asia/Novosibirsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Yakutsk",
  "Asia/Vladivostok",
  "Asia/Magadan",
  "Asia/Kamchatka",
];

export function getTimeZones() {
  const intlWithValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: "timeZone") => string[];
  };
  if (typeof intlWithValues.supportedValuesOf === "function") {
    return intlWithValues.supportedValuesOf("timeZone");
  }
  return fallbackTimeZones;
}

export function formatTimeZoneLabel(timeZone: string) {
  try {
    const formatter = new Intl.DateTimeFormat("ru-RU", {
      timeZone,
      timeZoneName: "shortOffset",
      hour: "2-digit",
      minute: "2-digit",
    });
    const offset = formatter.formatToParts(new Date()).find((part) => part.type === "timeZoneName")?.value;
    return offset ? `${timeZone} (${offset})` : timeZone;
  } catch {
    return timeZone;
  }
}
