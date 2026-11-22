import type { SceneId } from '../content';
import type { SceneModule } from './types';

export const SCENE_ORDER: SceneId[] = ['hero','problem','pipeline','policy','injection','minimization','anomaly','reasoner','queue','audit','results','closing'];

const modules = import.meta.glob<{ default: SceneModule }>('../scenes/*.ts', { eager: true });

/** Registered scene modules in SCENE_ORDER. Missing scenes are skipped. */
export function registeredScenes(): SceneModule[] {
  const byId = new Map<SceneId, SceneModule>();
  for (const [path, mod] of Object.entries(modules)) {
    const file = path.split('/').pop()!.replace(/\.ts$/, '');
    const scene = mod?.default;
    if (!scene || !SCENE_ORDER.includes(file as SceneId)) {
      console.warn(`[leash] ignoring scene file with unknown id: ${path}`);
      continue;
    }
    if (scene.id !== file) {
      console.warn(`[leash] scene file ${path} declares id ${String(scene.id)}; skipped`);
      continue;
    }
    byId.set(scene.id, scene);
  }
  return SCENE_ORDER.flatMap((id) => (byId.has(id) ? [byId.get(id)!] : []));
}
