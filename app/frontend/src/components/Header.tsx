import { useState } from 'react';
import type { Api } from '../api/client';
import { describeError } from '../api/errors';
import { DEMO_SPEEDS, type DemoState, type Role, type State } from '../api/types';
import { formatClock } from '../lib/format';
import { ROLE_LABEL } from '../lib/labels';
import type { Identity } from '../store/identity';
import { PauseIcon, PlayIcon, ResetIcon } from './icons';

type DemoProps = {
  api: Api;
  demo: DemoState | null;
  onState: (s: State) => void;
  onError: (message: string) => void;
};

export function DemoControls({ api, demo, onState, onError }: DemoProps) {
  const [pending, setPending] = useState(false);
  const run = async (fn: () => Promise<State>) => {
    setPending(true);
    try {
      onState(await fn());
    } catch (e) {
      onError(describeError(e, 'demo'));
    } finally {
      setPending(false);
    }
  };
  const disabled = pending || !demo;
  const finished = demo ? demo.t >= demo.duration : false;
  return (
    <div className="demo" role="group" aria-label="Demo controls">
      <div className="clock num" aria-label="Demo clock">
        {demo ? `${formatClock(demo.t)} / ${formatClock(demo.duration)}` : '-:--'}
        <small>{!demo ? 'demo clock' : finished ? 'demo finished' : demo.playing ? `playing ${demo.speed}x` : 'paused'}</small>
      </div>
      {demo?.playing ? (
        <button type="button" onClick={() => run(api.demoPause)} disabled={disabled}>
          <PauseIcon className="vicon" /> Pause
        </button>
      ) : (
        <button type="button" className="primary" onClick={() => run(api.demoPlay)} disabled={disabled || finished}>
          <PlayIcon className="vicon" /> Play
        </button>
      )}
      <button
        type="button"
        onClick={() => {
          if (window.confirm('Reset the demo? All Inspections and Confirmations are cleared.')) void run(api.demoReset);
        }}
        disabled={disabled}
      >
        <ResetIcon className="vicon" /> Reset
      </button>
      <div className="seg" role="group" aria-label="Demo speed">
        {DEMO_SPEEDS.map((s) => (
          <button key={s} type="button" aria-pressed={demo?.speed === s} disabled={disabled} onClick={() => run(() => api.demoSpeed(s))}>
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
}

type RoleProps = { identity: Identity; setRole: (r: Role) => void; setName: (n: string) => void };

/** Stands in for sign-in. The role and name go with every Confirmation. */
export function RoleSwitch({ identity, setRole, setName }: RoleProps) {
  const name = identity.names[identity.role];
  return (
    <div className="identity">
      <div className="seg" role="group" aria-label="Role">
        {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
          <button key={r} type="button" aria-pressed={identity.role === r} onClick={() => setRole(r)}>
            {ROLE_LABEL[r]}
          </button>
        ))}
      </div>
      <label className="field">
        Name
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
          aria-invalid={name.trim() === ''}
          autoComplete="off"
        />
      </label>
    </div>
  );
}
