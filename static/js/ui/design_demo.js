import { html, render } from './html.js';
import { dataState } from './data_state.js';

render([
  dataState('loading', 'Загружаем парк…'),
  dataState('empty', 'Парк пока пуст'),
  dataState('filtered', 'Нет каров по фильтру', html`<button class="btn btn-sm">Сбросить фильтры</button>`),
  dataState('error', 'Парк не загрузился. Проверьте связь и повторите.', html`<button class="btn btn-sm">Повторить</button>`),
], document.querySelector('#ds-data-states'));
