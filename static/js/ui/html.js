/* Шаблоны разметки: lit-html экранирует вставки по умолчанию (ADR-0013, раздел 7).
   Библиотека лежит в static/vendor/lit-html/ целиком, без сборки и внешних адресов.
   Экраны используют только этот вход: прямой innerHTML и ручной esc() уходят вместе с
   переносом разделов. */
export { html, svg, nothing, render } from '/static/vendor/lit-html/lit-html.js';
/* Переходная мера: unsafeHTML вставляет строку как разметку. Только для строк, которые старый код уже
   собрал и экранировал через esc() (тела модальных окон, v4Contacts…); новый код передаёт шаблоны.
   Уходит вместе с последним потребителем (шаг 6з). */
export { unsafeHTML } from '/static/vendor/lit-html/directives/unsafe-html.js';
