import type { SceneId } from '../content';
import { TALK, pick } from './talk';
import type { SceneModule } from './types';

/** Every scene file that exists. What is shown, and in what order, is set by TALK in ./talk.ts. */
export const SCENE_ORDER: SceneId[] = ['hero','problem','pipeline','policy','injection','minimization','anomaly','reasoner','queue','audit','demo','results','closing'];

const modules = import.meta.glob<{ default: SceneModule }>('../scenes/*.ts', { eager: true });

/** The talk's parts in speaking order, each cut from its scene. Parts whose scene is missing are skipped. */
export function registeredScenes(): SceneModule[] {
  const byId = new Map<string, SceneModule>();
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
  return TALK.flatMap((part) => {
    const scene = byId.get(part.from);
    return scene ? [pick(scene, part)] : [];
  });
}
