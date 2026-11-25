/** Точка входа: связывает элементы страницы и состояния интерфейса. */

import { ApiError, structureText } from "./api.js";
import { copyText, createToaster } from "./clipboard.js";
import { renderSections, sectionsToText } from "./render.js";
import { createTextareaController } from "./textarea.js";

const MAX_LENGTH = 5000;
const MIN_LENGTH = 10;

const el = {
  form: document.getElementById("form"),
  input: document.getElementById("input"),
  submit: document.getElementById("submit"),
  submitLabel: document.getElementById("submitLabel"),
  spinner: document.getElementById("spinner"),
  counter: document.getElementById("counter"),
  hint: document.getElementById("hint"),
  emptyIllustration: document.getElementById("emptyIllustration"),
  skeleton: document.getElementById("skeleton"),
  result: document.getElementById("result"),
  resultBody: document.getElementById("resultBody"),
  copy: document.getElementById("copy"),
  reset: document.getElementById("reset"),
  warning: document.getElementById("warning"),
  error: document.getElementById("error"),
  errorText: document.getElementById("errorText"),
  retry: document.getElementById("retry"),
  errorReset: document.getElementById("errorReset"),
  statusRegion: document.getElementById("statusRegion"),
  toast: document.getElementById("toast"),
  limitFill: document.getElementById("limitFill"),
};

const controller = createTextareaController(el.input, el.counter, el.hint, el.limitFill);
const notify = createToaster(el.toast);

const DEFAULT_HINT = el.hint.textContent;

const motionQuery =
  typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

function prefersReducedMotion() {
  return motionQuery ? motionQuery.matches : false;
}

let lastText = "";
let sections = [];
let isLoading = false;
let hintTimer = 0;

/* --- Состояния ----------------------------------------------------------- */

function setHint(message, isError) {
  window.clearTimeout(hintTimer);
  el.hint.textContent = message;
  el.hint.hidden = false;
  if (isError) {
    el.hint.dataset.state = "error";
  } else {
    delete el.hint.dataset.state;
  }
}

function resetHintSoon() {
  window.clearTimeout(hintTimer);
  hintTimer = window.setTimeout(() => {
    setHint(DEFAULT_HINT, false);
    updateSubmitState();
  }, 3000);
}

function announce(message) {
  el.statusRegion.textContent = "";
  // Повторная установка того же текста не озвучивается — сбрасываем.
  requestAnimationFrame(() => {
    el.statusRegion.textContent = message;
  });
}

function hide(node) {
  node.hidden = true;
}

function show(node) {
  node.hidden = false;
}

function updateSubmitState() {
  const length = controller.length;
  const valid = length >= MIN_LENGTH && length <= MAX_LENGTH;
  el.submit.disabled = !valid || isLoading;
  el.emptyIllustration.hidden = length > 0;

  // Подсказка про минимум нужна только пока текста мало.
  if (el.hint.dataset.state !== "error") {
    el.hint.hidden = length >= MIN_LENGTH;
  }
}

function setLoading(value) {
  isLoading = value;
  el.submit.disabled = value || controller.length < MIN_LENGTH;
  el.spinner.hidden = !value;
  el.submitLabel.textContent = value ? "Проясняю мысли..." : "Структурировать мысли";
  el.submit.setAttribute("aria-busy", String(value));
  el.input.readOnly = value;
  el.skeleton.hidden = !value;
  if (value) {
    hide(el.result);
    hide(el.warning);
    hide(el.error);
  }
}

function showError(message) {
  el.errorText.textContent = message;
  show(el.error);
  announce(message);
}

function clearAll() {
  hide(el.result);
  hide(el.warning);
  hide(el.error);
  el.resultBody.replaceChildren();
  sections = [];
}

/* --- Основной сценарий --------------------------------------------------- */

async function requestStructure() {
  const text = el.input.value.trim();

  if (text.length < MIN_LENGTH) {
    setHint("Напишите хотя бы пару предложений — так выйдет лучше.", true);
    resetHintSoon();
    el.input.focus();
    return;
  }

  if (text.length > MAX_LENGTH) {
    setHint("Можно не больше 5000 знаков — самое важное поместится", true);
    resetHintSoon();
    return;
  }

  lastText = text;
  clearAll();
  setLoading(true);

  try {
    const data = await structureText(text);
    sections = Array.isArray(data.sections) ? data.sections : [];

    renderSections(el.resultBody, sections);
    show(el.result);

    if (data.hasRedFlags) {
      show(el.warning);
    }

    announce("Готово. Результат появился ниже.");
    el.result.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  } catch (error) {
    const message =
      error instanceof ApiError
        ? error.message
        : "Что-то пошло не так на нашей стороне. Ваш текст никуда не делся — попробуйте ещё раз.";
    showError(message);
  } finally {
    setLoading(false);
    updateSubmitState();
  }
}

/* --- Копирование --------------------------------------------------------- */

async function handleCopy() {
  if (!sections.length) return;
  const ok = await copyText(sectionsToText(sections));
  notify(ok ? "Скопировали" : "Не удалось скопировать");
}

/* --- Сброс --------------------------------------------------------------- */

function handleReset() {
  clearAll();
  controller.reset();
  setHint(DEFAULT_HINT, false);
  updateSubmitState();
  el.input.focus();
  window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
}

/* --- Подписки ------------------------------------------------------------ */

el.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!isLoading) requestStructure();
});

el.input.addEventListener("input", () => {
  if (el.hint.dataset.state === "error") {
    setHint(DEFAULT_HINT, false);
  }
  updateSubmitState();
});
el.input.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    if (!el.submit.disabled) requestStructure();
  }
});

el.copy.addEventListener("click", handleCopy);
el.reset.addEventListener("click", handleReset);
el.retry.addEventListener("click", () => {
  hide(el.error);
  if (lastText) {
    el.input.value = lastText;
    controller.resize();
    controller.updateCounter();
    requestStructure();
  }
});
el.errorReset.addEventListener("click", handleReset);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !el.toast.hidden) {
    el.toast.dataset.visible = "false";
    el.toast.hidden = true;
  }
});

/* --- Старт --------------------------------------------------------------- */

controller.resize();
controller.updateCounter();
updateSubmitState();
