/* Реестр разделов: файл модуля сообщает загрузчики разделов (views: id → load) и экраны
   Настроек (screens: id → {render, icon}). Подписи, порядок и права пунктов — в манифесте
   модуля на сервере.
   Реестр живёт отдельным файлом без зависимостей: модули разделов вызывают registerModule при
   загрузке, а app.js и модули импортируют друг друга по кругу — реестр в app.js ещё не
   был бы создан в этот момент. */
export const MODULE_VIEWS = {};
export const MODULE_SCREENS = {};
const PALETTE_PROVIDERS = new Map();
export function registerModule({ views = {}, screens = {} }) {
  Object.assign(MODULE_VIEWS, views);
  Object.assign(MODULE_SCREENS, screens);
}

export function registerPaletteProvider(provider) {
  if (!provider?.id || typeof provider.search !== 'function' || typeof provider.activate !== 'function') {
    throw new TypeError('Palette provider requires id, search(query, signal), and activate(item)');
  }
  PALETTE_PROVIDERS.set(provider.id, provider);
  return () => { if (PALETTE_PROVIDERS.get(provider.id) === provider) PALETTE_PROVIDERS.delete(provider.id); };
}

export function unregisterPaletteProvider(id) { PALETTE_PROVIDERS.delete(id); }
export function paletteProviders() { return [...PALETTE_PROVIDERS.values()]; }
