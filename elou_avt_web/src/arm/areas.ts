/**
 * Участки установки для режима АРМ.
 *
 * Названия взяты из регламента ЭЛОУ-АВТ (раздел 3 «Описание технологического
 * процесса»). Принадлежность оборудования участку не зашита списком, а
 * считается по схеме: узел относится к тому участку, чей якорный аппарат
 * ближе по связям. Поэтому правка схемы не ломает разбиение.
 */
export interface Area {
  id: string;
  label: string;
  /** Ключевые аппараты участка по регламенту. */
  anchors: string[];
}

export const AREAS: Area[] = [
  { id: 'preheat1', label: 'Подогрев сырой нефти', anchors: ['hea_10', 'hea_12', 'hea_17', 'hea_18', 'hea_19', 'hea_20'] },
  { id: 'elou', label: 'Блок ЭЛОУ', anchors: ['elo_14', 'elo_15', 'elo_16', 'elo_28', 'elo_29', 'elo_30', 'sep_31'] },
  { id: 'preheat2', label: 'Подогрев обессоленной нефти', anchors: ['hea_33', 'hea_36', 'hea_37', 'hea_38', 'hea_40', 'hea_41', 'hea_43'] },
  { id: 'atm', label: 'Атмосферный блок', anchors: ['col_32', 'col_63', 'col_64', 'hea_53', 'hea_54', 'hea_66', 'sep_48', 'sep_94'] },
  { id: 'stab', label: 'Стабилизация бензина', anchors: ['col_51', 'sep_124'] },
  { id: 'secondary', label: 'Вторичная перегонка бензина', anchors: ['col_140', 'col_141', 'hea_142', 'sep_147'] },
];

/**
 * Узел → участок: волна по графу от якорей, побеждает ближайший.
 * Узлы без связей остаются без участка и показываются только на обзорной.
 */
export function assignAreas(
  nodeIds: string[],
  edges: { source: string; target: string }[],
): Record<string, string> {
  const adj = new Map<string, string[]>();
  const link = (a: string, b: string) => {
    const l = adj.get(a);
    if (l) l.push(b);
    else adj.set(a, [b]);
  };
  for (const e of edges) { link(e.source, e.target); link(e.target, e.source); }

  const owner: Record<string, string> = {};
  const known = new Set(nodeIds);
  let wave: string[] = [];
  for (const a of AREAS) {
    for (const anchor of a.anchors) {
      if (known.has(anchor) && !owner[anchor]) {
        owner[anchor] = a.id;
        wave.push(anchor);
      }
    }
  }
  while (wave.length) {
    const next: string[] = [];
    for (const cur of wave) {
      for (const n of adj.get(cur) ?? []) {
        if (!owner[n] && known.has(n)) { owner[n] = owner[cur]; next.push(n); }
      }
    }
    wave = next;
  }
  return owner;
}
