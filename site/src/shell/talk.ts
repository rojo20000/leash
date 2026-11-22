// The talk, in speaking order. Edit this file to change what is on screen:
// each part reuses one scene's picture, `step` picks which moment of that picture to stop on,
// and headline / sentence / callouts are the words shown beside it.
// Speakers: Zarek, Rowan, (Sal runs the system live, no slides), Nico. Source: `Script` on main.
import type { SceneId } from '../content';
import type { Callout, CalloutKind, Callouts, SceneModule, Verdict } from './types';

export interface Beat { step: number; headline: string; sentence: string; callouts: Callouts }
export interface Part { id: string; from: SceneId; title: string; beats: Beat[] }

const c = (text: string, kind: CalloutKind = 'name', verdict?: Verdict): Callout =>
  verdict ? { text, kind, verdict } : { text, kind };

export const TALK: Part[] = [
  // ---- Zarek: hook and problem ----
  {
    id: 'title', from: 'hero', title: 'Leash',
    beats: [{
      step: 0,
      headline: 'One simple job',
      sentence: 'A hospital gives an AI agent one simple job: schedule a patient from a referral.',
      callouts: [c('Tidal Byte 2026'), c('All patient data is synthetic')],
    }],
  },
  {
    id: 'problem', from: 'problem', title: 'The problem',
    beats: [
      {
        step: 0,
        headline: 'A referral arrives',
        sentence: 'The referral is a PDF. Reading it is part of the agent’s normal work.',
        callouts: [c('Scheduling agent'), c('Referral PDF')],
      },
      {
        step: 1,
        headline: 'One instruction is hidden inside',
        sentence: 'It tells the agent to send the patient’s records somewhere else.',
        callouts: [c('One hidden instruction'), c('Written for the agent, not the clinic')],
      },
      {
        step: 2,
        headline: 'The agent follows it',
        sentence: 'In our demo, the agent emails the full record for patient 0042 to an outside clinic address nobody approved.',
        callouts: [c('Scripted replay of the attack'), c('A live agent obeyed it in 1 of 3 runs')],
      },
      {
        step: 3,
        headline: 'The full record leaves',
        sentence: 'No one broke in. The agent just followed instructions. The wrong ones.',
        callouts: [c('3,965 characters of patient record', 'figure'), c('Sent to an outside address'), c('All patient data is synthetic')],
      },
    ],
  },

  // ---- Rowan: solution and who it is for ----
  {
    id: 'leash', from: 'hero', title: 'What Leash does',
    beats: [
      {
        step: 0,
        headline: 'A runtime security gateway for clinical AI agents',
        sentence: 'Runtime means it works while the agent is acting, not after the damage is done.',
        callouts: [c('Leash'), c('Checks every action as it happens')],
      },
      {
        step: 1,
        headline: 'Every tool call goes through Leash first',
        sentence: 'That covers every record the agent reads and every email it sends. Leash checks each one against the rules for the agent’s job, strips patient data down to what the task needs, scores it with machine learning, and logs it.',
        callouts: [c('Rules for the job'), c('Only the data the task needs'), c('Scored and logged')],
      },
      {
        step: 2,
        headline: 'Then it decides',
        sentence: 'Allow the call, block it, or hold it for a human.',
        callouts: [c('Allow', 'code', 'allow'), c('Block', 'code', 'block'), c('Hold for a human', 'code', 'hold')],
      },
      {
        step: 2,
        headline: 'Who it is for',
        sentence: 'Hospitals that want AI agents in their records systems, and the people who review what those agents do.',
        callouts: [c('Hospitals'), c('Reviewers'), c('The worst case is limited'), c('Every decision is logged')],
      },
    ],
  },

  // ---- Sal: live demo, no slides ----

  // ---- Nico: impact, what is next, close ----
  {
    id: 'results', from: 'results', title: 'Results',
    beats: [
      {
        step: 5,
        headline: '245 test calls',
        sentence: 'Leash approved 71 percent on its own, held 16 percent for a human, and blocked 12 percent.',
        callouts: [c('71% approved', 'figure', 'allow'), c('16% held', 'figure', 'hold'), c('12% blocked', 'figure', 'block')],
      },
      {
        step: 3,
        headline: '85 percent of hidden instructions caught',
        sentence: 'That is on test notes the detector had never seen, with zero false alarms.',
        callouts: [c('85% caught', 'figure'), c('0 false alarms', 'figure'), c('300 test notes', 'figure')],
      },
      {
        step: 1,
        headline: '7 to 8 milliseconds per call',
        sentence: 'That is what Leash adds with the NVIDIA model checks switched off and simple local stand-ins in their place.',
        callouts: [c('7 to 8 ms added', 'figure'), c('Each live NVIDIA call adds about 0.7 s', 'figure')],
      },
    ],
  },
  {
    id: 'rule', from: 'hero', title: 'The one thing to remember',
    beats: [{
      step: 3,
      headline: 'AI judgment where it helps humans decide',
      sentence: 'Hard rules where safety requires them. Nemotron can add caution. It can never remove it.',
      callouts: [c('NVIDIA Nemotron'), c('Nothing a model says can unblock a call')],
    }],
  },
  {
    id: 'next', from: 'closing', title: 'What is next',
    beats: [{
      step: 3,
      headline: 'This is a prototype',
      sentence: 'Synthetic data, one role, one policy. Next: policies for more roles, and a behavior model for tools people use directly.',
      callouts: [c('Synthetic data'), c('One role, one policy'), c('Not a compliance claim')],
    }],
  },
  {
    id: 'demo', from: 'demo', title: 'Clinic Assistant',
    beats: [{
      step: 1,
      headline: 'Clinic Assistant',
      sentence: 'Sal’s tool for clinic staff, recorded here on its own. It can already send its patient lookups through Leash, a setting that is off by default.',
      callouts: [c('Screen recording'), c('All patient data is synthetic')],
    }],
  },
  {
    id: 'close', from: 'hero', title: 'Thank you',
    beats: [{
      step: 0,
      headline: 'Keep them on a Leash',
      sentence: 'Hospitals don’t have to keep AI agents out. They just have to keep them on a Leash.',
      callouts: [c('Zarek'), c('Sal'), c('Rowan'), c('Nico')],
    }],
  },
];

/**
 * A scene cut down to the chosen beats. The scene's own picture is untouched: each beat stops at
 * the middle of its original step, and moving between beats plays the picture from one to the other.
 */
export function pick(mod: SceneModule, part: Part): SceneModule {
  const n = mod.steps().length;
  const mids = part.beats.map((b) => (Math.min(n - 1, Math.max(0, b.step)) + 0.5) / n);
  const k = mids.length;
  const toOriginal = (u: number): number => {
    const x = u - 0.5; // distance from the first beat's stop, in beats
    if (x <= 0) return mids[0] + x / n;
    if (x >= k - 1) return mids[k - 1] + (x - (k - 1)) / n;
    const i = Math.floor(x);
    return mids[i] + (x - i) * (mids[i + 1] - mids[i]);
  };
  return {
    id: part.id,
    base: mod.id as SceneId,
    title: part.title,
    steps: () => part.beats.map(({ headline, sentence, callouts }) => ({ headline, sentence, callouts })),
    mount(ctx) {
      const handle = mod.mount(ctx);
      return {
        update(f) {
          const p = Math.min(1, Math.max(0, toOriginal(f.progress * k)));
          const step = Math.min(n - 1, Math.floor(p * n));
          handle.update({ progress: p, step, stepProgress: p * n - step });
        },
        resize: handle.resize ? () => handle.resize!() : undefined,
      };
    },
  };
}
