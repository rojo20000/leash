import type { SceneId } from '../content';

/** Ground per scene: black scenes are the deliberate high-contrast beats. */
export const SCENE_GROUND: Record<SceneId, 'white' | 'black'> = {
  hero: 'white',
  problem: 'black',
  pipeline: 'white',
  policy: 'white',
  injection: 'black',
  minimization: 'white',
  anomaly: 'white',
  reasoner: 'black',
  queue: 'white',
  audit: 'black',
  demo: 'white',
  results: 'white',
  closing: 'white',
};
