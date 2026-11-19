/* Реестр разделов: файл модуля сообщает загрузчики разделов (views: id → load) и экраны
   Настроек (screens: id → {render, icon}). Подписи, порядок и права пунктов — в манифесте
   модуля на сервере.
   Реестр живёт отдельным файлом без зависимостей: модули разделов вызывают registerModule при
   загрузке, а app.js и модули импортируют друг друга по кругу — реестр в app.js ещё не
   был бы создан в этот момент. */
export const MODULE_VIEWS = {};
export const MODULE_SCREENS = {};
export function registerModule({ views = {}, screens = {} }) {
  Object.assign(MODULE_VIEWS, views);
  Object.assign(MODULE_SCREENS, screens);
}
