import { html, nothing } from './html.js';

export function dataState(kind, message, action = nothing) {
  return html`<div class="data-state" data-state=${kind}>
    <span role="status">${message}</span>
    ${action}
    ${kind === 'loading' ? html`<div class="skel-wrap" aria-hidden="true">
      <div class="skel-line skel-lg"></div><div class="skel-line"></div>
    </div>` : nothing}
  </div>`;
}
