import { content } from '../content';
import type { SceneId, Table } from '../content';

/** Exact label; throws if absent. */
export function fact(scene: SceneId, label: string): string {
  const hit = content[scene].facts.find((f) => f.label === label);
  if (!hit) throw new Error(`fact not found: ${scene}/${label}`);
  return hit.value;
}

/** The one quote containing needle, trimmed; throws on 0 or 2+ matches. */
export function quote(scene: SceneId, needle: string): string {
  const hits = content[scene].quotes.filter((q) => q.includes(needle));
  if (hits.length !== 1) throw new Error(`quote ${scene}/${needle}: ${hits.length} matches`);
  return hits[0].trim();
}

/** Exact table id; throws if absent. */
export function table(scene: SceneId, id: string): Table {
  const hit = content[scene].tables.find((t) => t.id === id);
  if (!hit) throw new Error(`table not found: ${scene}/${id}`);
  return hit;
}
