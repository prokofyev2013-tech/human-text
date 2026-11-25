/** Копирование в буфер и тост-уведомление. */

const TOAST_DURATION = 2000;
const CLIPBOARD_TIMEOUT = 1200;

export function createToaster(toast) {
  let timer = 0;

  return function notify(message = "Скопировали") {
    const label = toast.querySelector("span");
    if (label) label.textContent = message;

    toast.hidden = false;
    // Даём браузеру применить hidden=false перед сменой состояния.
    requestAnimationFrame(() => {
      toast.dataset.visible = "true";
    });

    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      toast.dataset.visible = "false";
      window.setTimeout(() => {
        toast.hidden = true;
      }, 220);
    }, TOAST_DURATION);
  };
}

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error("timeout")), ms);
    }),
  ]);
}

function legacyCopy(text) {
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;

  try {
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    // Держим элемент в текущей точке просмотра: иначе select() уводит скролл.
    helper.style.position = "fixed";
    helper.style.top = "0";
    helper.style.left = "0";
    helper.style.width = "1px";
    helper.style.height = "1px";
    helper.style.padding = "0";
    helper.style.border = "0";
    helper.style.opacity = "0";
    helper.style.pointerEvents = "none";
    document.body.append(helper);
    helper.select();
    helper.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    helper.remove();
    return ok;
  } catch {
    return false;
  } finally {
    // Возвращаем позицию даже при ошибке.
    if (window.scrollX !== scrollX || window.scrollY !== scrollY) {
      window.scrollTo(scrollX, scrollY);
    }
  }
}

/**
 * Копирует текст. Clipboard API доступен только в secure context
 * и может «зависнуть» без разрешения, поэтому есть таймаут
 * и запасной путь через временный textarea.
 */
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await withTimeout(navigator.clipboard.writeText(text), CLIPBOARD_TIMEOUT);
      return true;
    } catch {
      // Переходим к запасному способу.
    }
  }

  return legacyCopy(text);
}
