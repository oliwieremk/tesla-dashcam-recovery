'use strict';
window.LANG = 'pl';
window.MESSAGES = {};
window.i18nReady = fetch('i18n.json').then(response => {
  if (!response.ok) throw new Error('Translation catalog could not be loaded.');
  return response.json();
}).then(messages => { window.MESSAGES = messages; });
function t(key, values = []) {
  const text = window.LANG === 'en' ? (window.MESSAGES[key] || key) : key;
  return text.replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match);
}
function locale() { return window.LANG === 'en' ? 'en-GB' : 'pl-PL'; }
function applyStaticLanguage() {
  document.documentElement.lang = window.LANG;
  document.querySelectorAll('[data-i18n]').forEach(element => { element.textContent = t(element.dataset.i18n); });
  for (const attribute of ['title', 'placeholder', 'aria-label']) {
    document.querySelectorAll(`[data-i18n-${attribute}]`).forEach(element => {
      element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
    });
  }
  document.querySelectorAll('[data-language]').forEach(button => {
    const selected = button.dataset.language === window.LANG;
    button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected));
  });
}
