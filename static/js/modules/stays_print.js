/* Печатный месяц из уже отфильтрованного ответа шахматки. В документ попадают
   подписи фильтров и строк, без ключей броней и гостей. */
import { authContextIsCurrent, esc, expireAuthContext, requireAuthOwnership, subscribeAuthContext, subscribeSessionRejection,
  toast } from '../core.js';
import { printSessionMatches, printWindow } from './docs.js';
import { staysPos, staysRowChanges } from './stays.js';
import { STAYS_STATUS } from './stays_forms.js';

function filterLabels(fund, filters, names) {
  const labels = [];
  const selected = (title, choices, ids, field) => {
    const values = ids.map(id => choices.find(item => item.id === id)?.[field] ?? `#${id}`);
    if (values.length) labels.push(`${title}: ${values.join(', ')}`);
  };
  selected('Где', fund.groups, filters.group_ids, 'title');
  selected('Категории', fund.categories, filters.category_ids, 'code');
  selected('Флаги', fund.flags, filters.flag_ids, 'title');
  selected('Вид', fund.kinds, filters.kind_ids, 'title');
  if (filters.escorted) labels.push('с сопровождением');
  if (names) {
    if (filters.special) labels.push('◆ особый гость');
    selected('VIP-код', fund.vip_codes || [], filters.vip_code_ids, 'code');
    if (filters.q.trim()) labels.push(`Поиск: ${filters.q.trim()}`);
  }
  return labels.join(' · ');
}

function bookingLabel(bar, names, full) {
  const parts = [STAYS_STATUS[bar.status] || 'Занято', `${bar.guests_count} гост.`];
  if (bar.overbooked) parts.push('овербукинг');
  if (names) {
    parts.push(bar.number, bar.special && '◆', bar.main_guest, bar.vip_code, bar.label?.title);
  }
  if (full) parts.push(bar.customer && `Заказчик: ${bar.customer}`, bar.note);
  return parts.filter(Boolean).join(' · ');
}

export function printStaysBoard(data, fund, filters, visibility, monthLabel) {
  const full = visibility === 'full';
  const names = full || visibility === 'names';
  const days = data.days.map(day => staysPos(day, 0));
  const entries = new Map();
  const add = (unit, start, end, label) => {
    if (end < days[0] || start > days[days.length - 1] + 1) return;
    if (!entries.has(unit)) entries.set(unit, []);
    entries.get(unit).push({ start, end, label });
  };
  for (const bar of data.bars) add(bar.unit_id, bar.start_pos, bar.end_pos, bookingLabel(bar, names, full));
  for (const hold of data.holds) add(hold.unit_id, hold.start_pos, hold.end_pos,
    names && hold.title ? `OOO · ${hold.title}` : 'OOO');
  for (const block of data.blocks) add(block.unit_id, block.start_pos, block.end_pos,
    names && block.title ? `Блок · ${block.title}` : 'Блок');

  const rows = [];
  const writeUnit = (id, caption) => {
    const events = entries.get(id) || [];
    if (!events.length) {
      rows.push(`<tr><th>${esc(caption)}</th><td>—</td><td colspan="${days.length}"></td></tr>`);
      return;
    }
    for (const { start, end, label } of events.sort((a, b) => a.start - b.start)) {
      const cells = days.map(am => {
        const morning = start <= am && am <= end;
        const evening = start <= am + 1 && am + 1 <= end;
        return `<td>${morning ? (evening ? '●' : '◐') : (evening ? '◑' : '')}</td>`;
      });
      rows.push(`<tr><th>${esc(caption)}</th><td>${esc(label)}</td>${cells.join('')}</tr>`);
    }
  };
  const cats = Object.fromEntries(fund.categories.map(c => [c.id, c]));
  for (const unit of data.units) {
    for (const [first, last, why] of unit.off) {
      add(unit.unit_id, staysPos(first, 0), staysPos(last, 1), why === 'absent' ? 'Нет в фонде' : 'Вне фильтра');
    }
    writeUnit(unit.unit_id, [unit.label, unit.category, staysRowChanges(unit, cats)].filter(Boolean).join(' · '));
  }
  if (entries.has(null)) writeUnit(null, 'Не распределено');
  const title = `Шахматка · ${monthLabel}`;
  const labels = filterLabels(fund, filters, names);
  const head = data.days.map(day => `<th>${Number(day.slice(8))}</th>`).join('');
  return printWindow(title, `<h1>${esc(title)}</h1>${labels ? `<p>${esc(labels)}</p>` : ''}
    <p>◐ утро · ◑ вечер · ● весь день</p>
    <table><thead><tr><th>Объект</th><th>Размещение</th>${head}</tr></thead><tbody>${rows.join('')}</tbody></table>
    ${rows.length ? '' : '<p>Объектов по фильтру нет</p>'}`, `
    table { table-layout: fixed; } th, td { padding: 1mm 0; overflow-wrap: anywhere; }
    tr { break-inside: avoid; } tr > :nth-child(-n+2) { text-align: left; padding-inline: 1mm; }
    thead th:first-child { width: 26mm; } thead th:nth-child(2) { width: 54mm; }`);
}


const previews = new Set();
function closePreviews() {
  for (const dismiss of previews) dismiss();
}
subscribeAuthContext(closePreviews);
subscribeSessionRejection(closePreviews);
window.addEventListener('pagehide', closePreviews);

export async function previewStaysPdf(path, filename, isCurrent, fallback) {
  let owner;
  try { owner = requireAuthOwnership(); }
  catch (error) { toast(error.message, 'err'); return; }
  // Safari и Chrome разрешают окно внутри обработчика клика, пока PDF ещё готовится.
  const preview = window.open('', '_blank');
  const controller = new AbortController();
  const request = { credentials: 'same-origin', cache: 'no-store', signal: controller.signal };
  let url, check, validating;

  function dismiss() {
    if (!previews.delete(dismiss)) return;
    controller.abort();
    clearInterval(check);
    window.removeEventListener('focus', validate);
    window.removeEventListener('pageshow', validate);
    document.removeEventListener('visibilitychange', onVisible);
    if (url) URL.revokeObjectURL(url);
    if (preview && !preview.closed) preview.close();
  }
  function current() {
    return !controller.signal.aborted && !preview?.closed && authContextIsCurrent(owner);
  }
  function onVisible() {
    if (!document.hidden) void validate();
  }
  function serverMatches() {
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]);
    return printSessionMatches(owner, { ...request, signal });
  }
  async function validate() {
    if (!current()) { dismiss(); return; }
    if (validating) return;
    validating = true;
    try {
      if (!await serverMatches() || !current()) dismiss();
    } catch { dismiss(); }
    finally { validating = false; }
  }

  previews.add(dismiss);
  try {
    const response = await fetch(path, request);
    if (!current() || !isCurrent()) { dismiss(); return; }
    if (response.status === 401) { dismiss(); await expireAuthContext(owner); return; }
    if (response.status === 502) {
      dismiss();
      toast('PDF недоступен. Открыта упрощённая печать.', 'warn');
      return fallback();
    }
    if (!response.ok) throw new Error(`Не удалось открыть PDF шахматки (${response.status})`);
    if (response.headers.get('X-Butler-Auth-Context') !== owner.context) { dismiss(); return; }
    const blob = await response.blob();
    if (!current() || !isCurrent() || !await serverMatches() || !current() || !isCurrent()) { dismiss(); return; }

    const blobUrl = URL.createObjectURL(blob);
    if (!preview) {
      dismiss();
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 4000);
      toast('PDF скачан. Откройте файл, чтобы распечатать шахматку.', 'warn');
      return;
    }
    url = blobUrl;
    preview.opener = null;
    preview.location.replace(url);
    check = setInterval(validate, 5000);
    window.addEventListener('focus', validate);
    window.addEventListener('pageshow', validate);
    document.addEventListener('visibilitychange', onVisible);
  } catch (error) {
    const cancelled = controller.signal.aborted;
    dismiss();
    if (!cancelled && isCurrent()) toast(error.message, 'err');
  }
}
