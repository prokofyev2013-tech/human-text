/** Работа с API. */

const ENDPOINT = "/api/structure-text";

/**
 * Отправляет текст на структурирование.
 * @param {string} text
 * @returns {Promise<{sections: Array, hasRedFlags: boolean, processingTime: number}>}
 */
export async function structureText(text) {
  let response;
  try {
    response = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch (cause) {
    throw new ApiError("network", "Нет связи с сервером.", cause);
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.error || "Что-то пошло не так на нашей стороне.";
    throw new ApiError(response.status, message);
  }

  return payload;
}

export class ApiError extends Error {
  constructor(status, message, cause) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.cause = cause;
  }
}
