import type { SceneFrame } from './types';

export function frameAt(scrollY: number, start: number, end: number, steps: number): SceneFrame {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const progress = clamp((scrollY - start) / Math.max(1, end - start));
  const scaled = progress * steps;
  const step = Math.min(steps - 1, Math.floor(scaled));
  return { progress, step, stepProgress: clamp(scaled - step) };
}
