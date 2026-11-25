/** Автоувеличение высоты поля ввода и счётчик знаков. */

const MIN_HEIGHT = 200;
const MAX_HEIGHT = 480;
const MAX_LENGTH = 5000;
const NEAR_LIMIT = 4500;

export function createTextareaController(textarea, counter, hint, limitFill) {
  function resize() {
    textarea.style.height = "auto";
    const contentHeight = textarea.scrollHeight;

    // Если содержимое меньше минимальной высоты, отдаём размер CSS.
    if (contentHeight <= MIN_HEIGHT) {
      textarea.style.height = "";
      textarea.style.overflowY = "hidden";
      return;
    }

    const next = Math.min(contentHeight, MAX_HEIGHT);
    textarea.style.height = `${next}px`;
    textarea.style.overflowY = contentHeight > MAX_HEIGHT ? "auto" : "hidden";
  }

  function updateCounter() {
    const length = textarea.value.length;
    counter.textContent = `${length} / ${MAX_LENGTH}`;

    if (length > NEAR_LIMIT) {
      counter.dataset.state = "near";
    } else {
      delete counter.dataset.state;
    }

    if (limitFill) {
      const percent = Math.min(100, (length / MAX_LENGTH) * 100);
      limitFill.style.width = `${percent.toFixed(2)}%`;
      if (length > NEAR_LIMIT) {
        limitFill.dataset.state = "near";
      } else {
        delete limitFill.dataset.state;
      }
    }
  }

  function handleInput() {
    if (textarea.value.length > MAX_LENGTH) {
      textarea.value = textarea.value.slice(0, MAX_LENGTH);
      showLimitHint();
    }
    resize();
    updateCounter();
  }

  let hintTimer = 0;
  const defaultHint = hint.textContent;

  function showLimitHint() {
    hint.textContent = "Можно не больше 5000 знаков — самое важное поместится";
    hint.dataset.state = "error";
    window.clearTimeout(hintTimer);
    hintTimer = window.setTimeout(() => {
      hint.textContent = defaultHint;
      delete hint.dataset.state;
    }, 3000);
  }

  function handlePaste(event) {
    const pasted = event.clipboardData?.getData("text") ?? "";
    const selectionStart = textarea.selectionStart ?? textarea.value.length;
    const selectionEnd = textarea.selectionEnd ?? textarea.value.length;

    const before = textarea.value.slice(0, selectionStart);
    const after = textarea.value.slice(selectionEnd);
    const available = MAX_LENGTH - before.length - after.length;

    if (pasted.length <= available) return;

    // Вставляем столько, сколько влезает: без execCommand и без потери ввода.
    event.preventDefault();
    textarea.value = before + pasted.slice(0, Math.max(0, available)) + after;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    showLimitHint();
  }

  textarea.addEventListener("input", handleInput);
  textarea.addEventListener("paste", handlePaste);

  return {
    resize,
    updateCounter,
    get length() {
      return textarea.value.trim().length;
    },
    reset() {
      textarea.value = "";
      resize();
      updateCounter();
      hint.textContent = defaultHint;
      delete hint.dataset.state;
    },
  };
}
