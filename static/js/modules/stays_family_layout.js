/* Раскладка графа: пары по возможности в одном поколении, родители всегда выше детей. */
export const FAMILY_CARD = { width: 184, height: 106 };
const COLUMN = 222;
const MARGIN = 28;
const TRACK = 23;
export const FAMILY_UNIONS = {
  spouse: 'Брак', spouseFormer: 'Бывший брак', partner: 'Партнёрство', partnerFormer: 'Бывшее партнёрство',
};
const unionKind = ({ kind, former }) => former ? kind + 'Former' : kind;
const pairKey = (a, b) => a < b ? `${a}:${b}` : `${b}:${a}`;
const average = values => values.reduce((sum, n) => sum + n, 0) / values.length;

/* Схлопываем пары, только если это не создаёт цикл из родительских связей.
   Например, партнёр может быть на поколение ниже в другом крыле дерева. */
function generations(ids, parentLinks, pairs) {
  const group = new Map(ids.map(id => [id, id]));
  const edges = () => {
    const out = new Map([...group.values()].map(id => [id, new Set()]));
    for (const { a, b } of parentLinks) out.get(group.get(a)).add(group.get(b));
    return out;
  };
  let next = edges();
  const reaches = (start, target) => {
    const stack = [start];
    const seen = new Set(stack);
    while (stack.length) {
      for (const id of next.get(stack.pop())) {
        if (id === target) return true;
        if (!seen.has(id)) { seen.add(id); stack.push(id); }
      }
    }
    return false;
  };
  for (const { a, b } of pairs) {
    const left = group.get(a);
    const right = group.get(b);
    if (left === right || reaches(left, right) || reaches(right, left)) continue;
    for (const [id, value] of group) if (value === right) group.set(id, left);
    next = edges();
  }

  const rank = new Map([...next.keys()].map(id => [id, 0]));
  const incoming = new Map(rank);
  for (const children of next.values()) for (const id of children) incoming.set(id, incoming.get(id) + 1);
  const ready = [...incoming.keys()].filter(id => !incoming.get(id));
  for (const id of ready) {
    for (const child of next.get(id)) {
      rank.set(child, Math.max(rank.get(child), rank.get(id) + 1));
      incoming.set(child, incoming.get(child) - 1);
      if (!incoming.get(child)) ready.push(child);
    }
  }
  return { group, rank };
}

function siblingLabels(root, people, parents, children, unions) {
  const up = parents.get(root);
  const labels = new Map();
  const gendered = (id, male, female, neutral) => ({ m: male, f: female }[people.get(id).gender] || neutral);
  for (const parent of up) {
    for (const id of children.get(parent)) {
      if (id === root) continue;
      const theirParents = parents.get(id);
      const shared = theirParents.filter(other => up.includes(other));
      if (shared.length > 1) {
        labels.set(id, gendered(id, 'Родной брат', 'Родная сестра', 'Два общих родителя'));
      } else {
        const side = gendered(parent, 'по отцу', 'по матери', '');
        const bothKnown = up.length > 1 && theirParents.length > 1;
        labels.set(id, side && bothKnown ? gendered(id, `Брат ${side}`, `Сестра ${side}`, `Общий родитель ${side}`)
          : 'Один известный общий родитель');
      }
    }
  }
  for (const { a, b, former } of unions) {
    if (former) continue;
    const stepParent = up.includes(a) ? b : up.includes(b) ? a : null;
    if (stepParent === null || up.includes(stepParent)) continue;
    for (const id of children.get(stepParent)) {
      if (id !== root && !labels.has(id) && !up.includes(id) && !children.get(root).includes(id)) {
        labels.set(id, gendered(id, 'Сводный брат', 'Сводная сестра', 'Сводный брат или сестра'));
      }
    }
  }
  return labels;
}

export function familyLayout(family, root) {
  const people = new Map(family.people.map(p => [p.id, p]));
  const ids = [...people.keys()];
  const links = family.links.filter(({ a, b }) => people.has(a) && people.has(b));
  const parentLinks = links.filter(link => link.kind === 'parent');
  const unions = links.filter(link => link.kind === 'spouse' || link.kind === 'partner')
    .sort((a, b) => Number(a.former) - Number(b.former));
  const parents = new Map(ids.map(id => [id, []]));
  const children = new Map(ids.map(id => [id, []]));
  for (const { a, b } of parentLinks) { parents.get(b).push(a); children.get(a).push(b); }

  const pairs = new Map(unions.map(link => [pairKey(link.a, link.b), link]));
  for (const [a, b] of parents.values()) {
    if (b !== undefined && !pairs.has(pairKey(a, b))) pairs.set(pairKey(a, b), { a, b });
  }
  const neighbours = new Map(ids.map(id => [id, []]));
  for (const { a, b } of pairs.values()) { neighbours.get(a).push(b); neighbours.get(b).push(a); }
  const { group, rank } = generations(ids, parentLinks, pairs.values());
  const rows = Array.from({ length: Math.max(0, ...rank.values()) + 1 }, () => new Map());
  for (const id of ids) {
    const key = group.get(id);
    const row = rows[rank.get(key)];
    if (!row.has(key)) row.set(key, []);
    row.get(key).push(id);
  }
  const counts = rows.map(row => [...row.values()].reduce((n, members) => n + members.length, 0));
  const gridWidth = Math.max(1, ...counts) * COLUMN;
  const positions = new Map();
  rows.forEach((row, level) => {
    const anchor = members => {
      const xs = members.flatMap(id => parents.get(id).map(parent => positions.get(parent)?.x)).filter(Number.isFinite);
      return xs.length ? average(xs) : gridWidth / 2;
    };
    const groups = [...row.values()].map(members => ({ members, x: anchor(members) })).sort((a, b) => a.x - b.x);
    const members = groups.flatMap(entry => {
      const remaining = [...entry.members].sort((a, b) => anchor([a]) - anchor([b]));
      const degree = id => neighbours.get(id).length;
      const ordered = [];
      while (remaining.length) {
        const next = neighbours.get(ordered.at(-1))?.find(id => remaining.includes(id))
          ?? remaining.reduce((min, id) => degree(id) < degree(min) ? id : min);
        ordered.push(next);
        remaining.splice(remaining.indexOf(next), 1);
      }
      return ordered;
    });
    members.forEach((id, i) => positions.set(id, { id, level,
      x: MARGIN + (gridWidth - counts[level] * COLUMN) / 2 + (i + 0.5) * COLUMN }));
  });

  /* Общие дети выходят из одного узла пары. При наличии брака/партнёрства
     ствол начинается на линии союза, иначе рисуем только родительские линии. */
  const families = new Map();
  for (const [id, up] of parents) {
    if (!up.length) continue;
    const key = [...up].sort((a, b) => a - b).join(':');
    if (!families.has(key)) families.set(key, { from: up, to: [] });
    families.get(key).to.push(id);
  }

  const lanes = rows.map(() => []);
  let width = gridWidth + 2 * MARGIN + 8;
  const reserve = (level, xs) => {
    const left = Math.min(...xs) - 12;
    const right = Math.max(...xs) + 12;
    const available = lanes[level];
    let lane = available.findIndex(used => used.every(([a, b]) => right < a || b < left));
    if (lane < 0) lane = available.push([]) - 1;
    available[lane].push([left, right]);
    return { level, lane };
  };
  const detour = (node, level) => {
    width += 8;
    const x = width - MARGIN;
    return { x, ...reserve(level, [node.x, x]) };
  };

  const ports = new Map();
  const source = id => {
    const point = { ...positions.get(id), port: positions.get(id).x };
    if (!ports.has(id)) ports.set(id, []);
    ports.get(id).push(point);
    return point;
  };

  const unionRoutes = new Map();
  for (const link of unions) {
    const a = source(link.a);
    const b = source(link.b);
    const [upper, lower] = a.level < b.level ? [a, b] : [b, a];
    const outer = upper.level === lower.level ? null : detour(upper, upper.level);
    const x = outer ? average([outer.x, lower.x]) : average([a.x, b.x]);
    const route = { a, b, x, outer, kind: unionKind(link), ...reserve(lower.level,
      [a.x, b.x, x - 82, x + 82, outer?.x ?? x]) };
    const key = pairKey(a.id, b.id);
    if (!unionRoutes.has(key)) unionRoutes.set(key, []);
    unionRoutes.get(key).push(route);
  }

  const familyRoutes = [...families.values()].map(({ from, to }) => {
    const union = from.length === 2 ? unionRoutes.get(pairKey(...from))?.[0] : null;
    const sources = from.map(id => union ? positions.get(id) : source(id));
    const level = Math.max(...sources.map(node => node.level));
    const outgoing = sources.map(node => ({ node, outer: node.level < level && !union ? detour(node, node.level) : null }));
    const targets = to.map(id => {
      const node = positions.get(id);
      return { ...node, outer: node.level > level + 1 ? detour(node, node.level - 1) : null };
    });
    const x = union?.x ?? average(sources.map(node => node.x));
    const xs = [x, ...outgoing.map(({ node, outer }) => outer?.x ?? node.x), ...targets.map(node => node.outer?.x ?? node.x)];
    return { outgoing, targets, union, x, ...reserve(level, xs) };
  });
  /* Разводим вход и выход на карточках одной колонки: вход идёт по центру,
     выходы — по сторонам. Для ствола общих детей выбираем свободную точку союза. */
  const verticals = rows.map(() => []);
  for (const points of ports.values()) {
    const middle = Math.ceil(points.length / 2);
    const step = Math.min(12, 110 / points.length);
    points.forEach((point, i) => {
      point.port += i < middle ? -7 - (middle - i - 1) * step : 7 + (i - middle) * step;
      verticals[point.level].push(point.port);
    });
  }
  for (const route of familyRoutes) {
    for (const node of route.targets) verticals[node.level - 1].push(node.x);
  }
  const unionSpan = ({ a, b, outer, level }) => outer
    ? [a.level === level ? a.port : b.port, outer.x] : [a.port, b.port];
  for (const route of familyRoutes.filter(item => item.union)) {
    const occupied = verticals[route.level];
    const [a, b] = unionSpan(route.union);
    const min = Math.min(a, b);
    const max = Math.max(a, b);
    const candidates = [route.x];
    for (let x = 8; x < max - min; x += 8) candidates.push(route.x + x, route.x - x);
    route.x = candidates.find(x => x > min && x < max && occupied.every(track => Math.abs(track - x) >= 7)) ?? route.x;
    occupied.push(route.x);
  }

  let height = MARGIN;
  const rowY = lanes.map(row => {
    const y = height;
    height += FAMILY_CARD.height + Math.max(54, 40 + row.length * TRACK);
    return y;
  });
  const bottom = node => rowY[node.level] + FAMILY_CARD.height;
  const bus = ({ level, lane }) => rowY[level] + FAMILY_CARD.height + 24 + lane * TRACK;
  const sourcePath = (node, y, outer) => outer === null
    ? `M ${node.port} ${bottom(node)} V ${y}`
    : `M ${node.port} ${bottom(node)} V ${bus(outer)} H ${outer.x} V ${y}`;
  const targetPath = (node, y) => node.outer === null
    ? `M ${node.x} ${y} V ${rowY[node.level]}`
    : `M ${node.outer.x} ${y} V ${bus(node.outer)} H ${node.x} V ${rowY[node.level]}`;
  const bar = (xs, y) => `M ${Math.min(...xs)} ${y} H ${Math.max(...xs)}`;

  const edges = [...unionRoutes.values()].flat().map(route => {
    const { a, b, x, kind, outer, level } = route;
    const y = bus(route);
    return { kind, x, y, label: FAMILY_UNIONS[kind],
      title: `${FAMILY_UNIONS[kind]}: ${people.get(a.id).name} и ${people.get(b.id).name}`,
      path: [sourcePath(a, y, a.level < level ? outer : null), sourcePath(b, y, b.level < level ? outer : null),
        bar(unionSpan(route), y)].join(' ') };
  });
  for (const route of familyRoutes) {
    const { outgoing, targets, union, x } = route;
    const y = bus(route);
    const parentNames = outgoing.map(({ node }) => people.get(node.id).name).join(' и ');
    const childNames = targets.map(node => people.get(node.id).name).join(', ');
    edges.push({
      kind: 'parent',
      title: `Родители: ${parentNames}. Дети: ${childNames}`,
      path: [
        union ? `M ${x} ${bus(union)} V ${y}` : outgoing.map(({ node, outer }) => sourcePath(node, y, outer)).join(' '),
        bar([...(union ? [x] : outgoing.map(({ node, outer }) => outer?.x ?? node.port)),
          ...targets.map(node => node.outer?.x ?? node.x)], y),
        ...targets.map(node => targetPath(node, y)),
      ].join(' '),
    });
  }

  const labels = siblingLabels(root, people, parents, children, unions);
  const kin = new Map(family.kin.map(relative => [relative.person_id, relative]));
  const nodes = [...positions.values()].map(({ id, level, x }) => {
    const relation = kin.get(id);
    const title = relation?.via_former && relation.degree > 0 ? `${relation.title} (через бывший союз)` : relation?.title;
    return { ...people.get(id), x, y: rowY[level], title: labels.get(id) || title || '' };
  });
  return { width, height, nodes, edges };
}
