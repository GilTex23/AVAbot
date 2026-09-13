import { ApiError } from "../services/api";

/** Понятный текст ошибки запроса к админке */
export function describeAdminError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "Сессия Telegram устарела — закройте и снова откройте мини-апп.";
    }
    if (error.status === 403) {
      return "Нет доступа к админке.";
    }
    if (error.status < 500 || error.status === 502) {
      return error.message;
    }
  }
  return fallback;
}
