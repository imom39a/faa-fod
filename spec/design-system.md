# Design system: the Ops console

Decided in issue 0019. This is how every screen of the dashboard looks and is laid out. `spec/dashboard-ux.md` says what each screen contains and how the workflow behaves; this file says how it is drawn. Read both before adding or changing a screen.

The product name in the UI is **StandClear** (`app/frontend/src/lib/brand.ts`).

## Who it is for

- A Ramp Lead with a landscape tablet at the gate or in a vehicle.
- A supervisor at a desk or a control-room screen.
- A Ramp Agent on a phone, as a fallback. The layout must hold together at phone width, but the tablet and desk are what it is tuned for.

These people look up from other work, often for a few seconds, sometimes with gloves on. The screen has to answer "is anything wrong, and where?" before they read a word.

## Principles

Each principle is followed by the rule that makes it checkable.

1. **Colour is for abnormal states.** The display is grey when everything is normal, so a HOLD is the only red thing on it. This follows high-performance HMI practice (ANSI/ISA-101).
   - Saturated colour is used only for HOLD, REMOVE, ADVISORY and INCOMPLETE.
   - Normal states (idle, on stand, inspecting, ALL CLEAR, confirmed clear) use the muted tokens.
   - Never use colour for decoration, branding, or to tell sections apart.
2. **Never colour alone.** Every severity, Verdict and status has a text label and an icon as well as its colour. A HOLD and an escalated Task differ by shape and text, not only by hue.
3. **The Gates are always in view.** The Gate strip sits at the top of every page. A new page must not hide it, cover it or scroll it away.
4. **Most urgent first.** Anything that lists work is ordered HOLDs first, then by time to scheduled pushback, and shows that order (a number, not just position).
5. **Advisory until a person confirms.** Anything that comes from the system alone carries the dashed "advisory" tag. Only a human Confirmation gets the solid "confirmed by a person" tag.
6. **Dense, but touchable.** Tables and rows are preferred to cards, and text is 14px, so more fits on a tablet. Every control is still at least 44px tall.
7. **Plain shapes.** Square corners, 1px lines, no gradients, no drop shadows except on a panel that floats over the page.
8. **Demo scaffolding stays out of the product.** The demo clock and the role switch live in the tray behind the clock button, not in the page chrome.

## Layout

```
+------+-----------------------------------------------------------+
| rail | Gate strip: one cell per Gate                 | demo tray |
|      +-----------------------------------------------------------+
|      | page                                                      |
+------+-----------------------------------------------------------+
```

- **Rail** (96px, left, dark): the product mark, one link per page with an icon and a label, and who is signed in at the bottom. The current page has a lighter background and a bar on its inner edge. The Chat link shows the signed-in person's open Task count, red if one is a HOLD.
- **Gate strip** (sticky, top): one cell per Gate with the Gate, the flight, the time to pushback and one status line. A cell is grey when normal and filled with its severity colour when abnormal. The cell of the Turn being viewed has a bar along its bottom edge. Each cell links to its Turn.
- **Page**: 14px padding, full width. A page with a main column and a side column puts the side column on the right at 380 to 420px.
- **Gates page** (`#/`): counters across the top, the Gates table on the left, the "Needs a human" queue on the right.

Widths:

| Width | What changes |
|---|---|
| over 1100px | As above. |
| 1100px and under | Side columns drop below the main column. The queue moves above the Gates table. The strip scrolls sideways. |
| 820px and under | The rail becomes a bar along the bottom. The Gates table drops the Verdict and severity columns (the strip and queue still show them). |

All of this is in `components/AppShell.tsx` and the "app shell" and "Gates page" sections of `styles.css`. A new page is a new entry in `PAGES` in `AppShell.tsx` plus a route; it gets the rail and the strip for free.

## Tokens

Every colour is a CSS variable defined once, in `:root` at the top of `app/frontend/src/styles.css`. No other rule, stylesheet or component may contain a literal colour.

| Group | Tokens | Use |
|---|---|---|
| Surfaces | `--bg`, `--panel`, `--panel-2`, `--panel-3` | Page, panel, raised row, inset or header row. |
| Lines | `--line`, `--line-strong` | Dividers; borders of controls and tables. |
| Ink | `--text`, `--muted`, `--faint` | Body text, secondary text, least important text. |
| Action | `--accent`, `--accent-ink` | Primary buttons, links, focus ring, selected state. Near-black, on purpose. |
| Abnormal | `--hold`, `--remove`, `--advisory`, `--incomplete` (and `--hold-ink`, `--remove-ink`) | Text, borders and fills for the four abnormal states. |
| Amber fill | `--caution-fill`, `--caution-fill-ink` | The fill of a REMOVE badge or cell. `--remove` is the dark amber used for text. |
| Normal | `--clear`, `--confirmed`, `--confirmed-ink`, `--await`, `--busy`, `--onstand`, `--idle`, `--closed` | Normal states. Muted so they do not compete. |
| On a fill | `--on-tone` | Text on any `--tone` fill. |
| Rail | `--rail`, `--rail-active`, `--rail-ink`, `--rail-muted` | The page rail only. |
| Photos | `--photo-bg`, `--photo-hi`, `--photo-lo`, `--photo-closed`, `--stamp-bg` | Marks drawn over photographs, which are dark whatever the theme. |
| Overlay | `--scrim`, `--shadow` | Behind a dialog; under a floating panel. |
| Size | `--radius` (3px), `--tap` (44px), `--rail-w` (96px) | Corners, minimum control height, rail width. |

A row, cell or card takes its colour from `--tone`, set by a `tone-*` class (`tone-hold`, `tone-remove`, `tone-confirmed` and so on; the list is the `Tone` type in `lib/gates.ts`). Use `isAbnormal(tone)` from `lib/gates.ts` to decide whether to draw it in colour.

Contrast: text on a panel, and text on a fill, is at least 4.5:1.

## Type

- System font stack. No web fonts: the app must work with no network.
- 14px body. 13px for secondary lines, 11 to 12px uppercase for column and section headings, 20 to 22px bold for a Gate number, 34px for a counter.
- Numbers that change (countdowns, counts, clocks) use the `num` class so digits do not shift.
- Labels use the words in `GLOSSARY.md` exactly.

## Components

Use these before making a new one.

| Need | Use | Where |
|---|---|---|
| A severity | `SeverityBadge` | `components/bits.tsx` |
| A Verdict with its advisory or confirmed tag | `VerdictMark`, `AdvisoryTag`, `ConfirmedTag` | `components/bits.tsx` |
| A status icon for a tone | `ToneIcon` | `components/icons.tsx` |
| A panel | `.panel` | `styles.css` |
| A section heading | `.section-title` | `styles.css` |
| A row with a coloured left edge | `.q-item`, `.fcard`, `.task-card`, `.act-row` | `styles.css` |
| A table of things with one row each | `.gate-table`, `.gt-row`; `table.kv` for key and value | `styles.css` |
| A counter | `.kpi` | `styles.css` |
| Buttons | `button`, `.primary`, `.good`, `.danger`, `.quiet`, `.compact`, `.big`; `.seg` for a segmented choice | `styles.css` |
| A message to the user | `.banner` with `.error`, `.warn`, `.ok` or `.info` | `styles.css` |
| A dialog | `.overlay` and `.dialog` | `styles.css` |

Buttons: `.primary` for the one main action of a view, `.good` for a Confirmation that clears something, `.danger` for an action that holds or refuses, plain for everything else. A Report button (which records nothing on the Inspection) has a dashed border so it cannot be mistaken for a Confirmation.

## Adding or changing a screen

1. Put it inside `AppShell`. Do not build a second header or navigation.
2. Lay it out from the components above. Prefer a table or rows to a grid of cards.
3. Use tokens only. If a new colour is truly needed, add a token to `:root`, add it to the table above, and add its contrast pair to `src/design.test.ts`.
4. Give every state a label and an icon, and decide whether it is normal or abnormal. If it is normal, it is not coloured.
5. Order any list of work most urgent first.
6. Check it at 1366px, 1024px and 430px wide, with a HOLD open and with nothing open.
7. Run `npm test`. `src/design.test.ts` fails if a literal colour appears outside `:root`, if `--tap` drops below 44px, or if a text and surface pair drops below 4.5:1.

## What the test does not check

`src/design.test.ts` cannot see whether colour is used only for abnormal states, whether a state has a label and an icon, or whether a layout holds at each width. Those are checked by reading the change against this file and looking at the screen.

## Sources

The principles come from ANSI/ISA-101 high-performance HMI practice (grey displays, colour reserved for abnormal conditions) and from field-service guidance on touch targets and glanceable status. The sources found were vendor articles and summaries of the standard, not the standard itself or a usability study with ramp crews. The prototype that compared this direction with two others is on the `prototype/field-ui` branch.
