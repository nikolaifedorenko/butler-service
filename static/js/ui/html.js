/* Шаблоны разметки: lit-html экранирует вставки по умолчанию (ADR-0013, раздел 7).
   Библиотека лежит в static/vendor/lit-html/ целиком, без сборки и внешних адресов.
   Экраны используют только этот вход; прямой innerHTML запрещён линтером. Разметку из строки
   (unsafeHTML) проект не вставляет нигде. */
export { html, svg, nothing, render } from '/static/vendor/lit-html/lit-html.js';

/* Корень для render() внутри контейнера, которым распоряжается не только шаблон. Остальной код вправе
   стереть содержимое раздела (при смене пользователя, при ошибке загрузки): lit хранит метки вывода в
   самом контейнере, и после innerHTML = '' следующий render() упал бы на оборванной метке
   («Cannot read properties of null (reading 'insertBefore')»). Корень создаётся заново, если его убрали. */
export function mount(host) {
  let root = host.querySelector(':scope > [data-lit-root]');
  if (!root) {
    host.replaceChildren();
    root = document.createElement('div');
    root.dataset.litRoot = '';
    root.style.display = 'contents';
    host.appendChild(root);
  }
  return root;
}
