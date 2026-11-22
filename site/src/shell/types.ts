import type { SceneId } from '../content';

export type Verdict = 'allow' | 'block' | 'hold';
export type CalloutKind = 'code' | 'figure' | 'name';
export interface Callout { text: string; kind: CalloutKind; verdict?: Verdict }
export type Callouts =
  | [Callout, Callout]
  | [Callout, Callout, Callout]
  | [Callout, Callout, Callout, Callout];
export interface StepCopy { headline: string; sentence: string; callouts: Callouts }

/** A pure function of scroll position. See section 6. */
export interface SceneFrame {
  progress: number;     // 0..1 across this scene's runway
  step: number;         // integer, 0..steps-1
  stepProgress: number; // 0..1 within the current step
}

export interface SceneContext {
  root: HTMLElement;   // <section class="scene scene-<id>">
  plate: HTMLElement;  // empty element the scene fills
  reducedMotion: boolean;
  isNarrow(): boolean; // live: viewport width <= 767px
}

export interface SceneHandle {
  update(frame: SceneFrame): void;
  resize?(): void; // rebuild px-based measurements; shell re-applies the frame after
}

export interface SceneModule {
  id: SceneId;
  title: string;            // rail title from section 1
  steps(): StepCopy[];      // number of steps is steps().length, at least 1
  mount(ctx: SceneContext): SceneHandle;
}
