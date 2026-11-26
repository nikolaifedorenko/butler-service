import { dateRu } from '../core.js';
import { html, nothing } from './html.js';

export const guestPickName = guest => [guest.last_name, guest.first_name, guest.middle_name].filter(Boolean).join(' ')
  || guest.name || guest.short;
export const guestPickDetails = guest => [guest.phone, dateRu(guest.birth_date)].filter(Boolean).join(' · ');

export function guestPickContent(guest, prefix = '', relation = '') {
  const details = [relation, guestPickDetails(guest)].filter(Boolean).join(' · ');
  return html`<span class="guest-pick-name">${prefix}${guestPickName(guest)}</span>
    ${details ? html`<small class="guest-pick-details muted">${details}</small>` : nothing}`;
}
