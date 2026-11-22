import type { SceneModule } from './types';

/** Fallback scene, shown only when no real scene registers or mounts. */
const placeholder: SceneModule = {
  id: 'hero',
  title: 'Leash',
  steps: () => [{
    headline: 'Scenes not added yet',
    sentence: 'The scenes for this page have not been added yet.',
    callouts: [
      { text: 'src/scenes', kind: 'code' },
      { text: 'No scene mounted', kind: 'name' },
    ],
  }],
  mount: ({ plate }) => {
    plate.textContent = 'No scenes yet.';
    return { update() {} };
  },
};
export default placeholder;
