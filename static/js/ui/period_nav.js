import { html } from './html.js';

export function periodNav(prefix, label, shift, unit = 'месяц') {
  const arrow = (direction, step, text, path) => html`<button type="button" id=${`${prefix}-${direction}`}
    title=${text} aria-label=${text} @click=${() => shift(step)}>
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d=${path}/></svg>
  </button>`;
  return html`<div class="month-nav">
    ${arrow('prev', -1, `Предыдущий ${unit}`, 'm10 3-5 5 5 5')}
    <div class="label" id=${`${prefix}-label`} tabindex="-1">${label}</div>
    ${arrow('next', 1, `Следующий ${unit}`, 'm6 3 5 5-5 5')}
  </div>`;
}
