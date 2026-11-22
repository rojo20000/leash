import gsap from 'gsap';
import { fact } from '../shell/content-access';
import { BEATS } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './demo.css';

const STEPS = 2;
const VIDEO_STEP = 1;
const SMALL = 0.55; // step 0 on desktop: the label sits in the plate column, beside the title

function steps(): StepCopy[] {
  const callouts: StepCopy['callouts'] = [
    { text: fact('demo', 'Kind'), kind: 'name' },
    { text: fact('hero', 'Data'), kind: 'name' },
  ];
  return [
    { headline: fact('demo', 'Title'), sentence: fact('demo', 'Title sentence'), callouts },
    { headline: fact('demo', 'Video title'), sentence: fact('demo', 'Video sentence'), callouts },
  ];
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  plate.textContent = '';
  const world = document.createElement('div');
  world.className = 'demo-world';
  const label = document.createElement('div');
  label.className = 'demo-label stock-label peel';
  const video = document.createElement('video');
  video.className = 'demo-video';
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  video.width = 1520;
  video.height = 855;
  video.controls = ctx.reducedMotion; // reduced motion: nothing autoplays, the visitor starts it
  video.setAttribute('aria-label', fact('demo', 'Video description'));
  for (const [file, type] of [['demo.webm', 'video/webm'], ['demo.mp4', 'video/mp4']]) {
    const source = document.createElement('source');
    source.src = import.meta.env.BASE_URL + file; // served from site/public
    source.type = type;
    video.append(source);
  }
  label.append(video);
  world.append(label);
  plate.append(world);

  const build = () => {
    const from = ctx.reducedMotion || ctx.isNarrow() ? 1 : SMALL;
    const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
    tl.to({}, { duration: STEPS }, 0);
    tl.fromTo(
      label,
      { scale: from, transformOrigin: '100% 50%' },
      { scale: 1, duration: BEATS.arrive - BEATS.diveStart, ease: 'power3.inOut' },
      VIDEO_STEP + BEATS.diveStart,
    );
    return tl;
  };
  let tl = build();
  let playing = false;

  return {
    update(f: SceneFrame) {
      tl.progress(f.progress);
      if (ctx.reducedMotion) return;
      // On while the presenter is on the video step: from the moment the label has grown to full
      // size until the scene's runway ends. Off before that (title step, or scenes above) and after.
      const on = f.step === VIDEO_STEP && f.stepProgress >= BEATS.arrive && f.progress < 1;
      if (on === playing) return;
      playing = on;
      if (on) {
        video.currentTime = 0;
        void video.play().catch(() => {}); // a pause that lands mid-start rejects; nothing to do
      } else {
        video.pause();
      }
    },
    resize() {
      // The start scale differs between narrow and desktop; the shell re-applies the frame after.
      tl.kill();
      tl = build();
    },
  };
}

const scene: SceneModule = { id: 'demo', title: 'Demo', steps, mount };
export default scene;
