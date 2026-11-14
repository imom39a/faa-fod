import { setDeveloperMode, useSettings } from '../store/settings';

/** Settings for this browser. Nothing here changes a Verdict, a Finding or what a person can do. */
export function SettingsPage() {
  const { developerMode } = useSettings();
  return (
    <div className="settings">
      <div className="turn-head">
        <h2 className="page-title">Settings</h2>
        <span className="muted small">Saved in this browser</span>
      </div>
      <section className="panel" aria-labelledby="settings-dev-h">
        <h3 id="settings-dev-h" className="section-title">
          Developer mode
        </h3>
        <p className="small muted">
          Shows details for the people who build and run the app: estimated model cost, tokens, LLM calls, stage timings, local models and
          which model decided each Finding, and the agent's session and wake cost. Ramp crews do not need these to do their work.
        </p>
        <div className="seg" role="group" aria-label="Developer mode">
          <button type="button" aria-pressed={!developerMode} onClick={() => setDeveloperMode(false)}>
            Off
          </button>
          <button type="button" aria-pressed={developerMode} onClick={() => setDeveloperMode(true)}>
            On
          </button>
        </div>
      </section>
    </div>
  );
}
