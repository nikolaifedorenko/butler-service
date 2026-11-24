/* Печатный месяц из уже отфильтрованного ответа шахматки. В документ попадают
   только подписи: внутренние ключи нужны исключительно для группировки строк. */
import { esc } from '../core.js';
import { printWindow } from './docs.js';
import { staysPos } from './stays.js';
import { STAYS_STATUS } from './stays_forms.js';

function filterLabels(fund, filters, names) {
  const labels = [];
  const selected = (title, choices, ids, field) => {
    const values = choices.filter(item => ids.includes(item.id)).map(item => item[field]);
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
  for (const unit of data.units) {
    for (const [first, last, why] of unit.off) {
      add(unit.unit_id, staysPos(first, 0), staysPos(last, 1), why === 'absent' ? 'Нет в фонде' : 'Вне фильтра');
    }
    writeUnit(unit.unit_id, [unit.label, unit.category].filter(Boolean).join(' · '));
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
