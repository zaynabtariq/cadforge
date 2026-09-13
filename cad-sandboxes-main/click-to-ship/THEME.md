# Part → Quote: visual foundation

A calm, modern product shell around a precise, model-focused workspace. The LoadLogic reference informs the white surfaces, mint fields, black actions, restrained borders, and spacious type. PreForm informs the dominant viewport, contextual tools, persistent model, and compact inspector.

Review the interactive study at http://127.0.0.1:8766/theme. Start, Build, and Quote show the same authored sample part. The conversation and quote fields are layout examples; the model controls work. The existing quote prototype at `/` uses the same foundation and retains its live workflow.

## Shared tokens

Source of truth: `web/theme.css`. Import it once per application stylesheet. `web/viewer.js` reads the scene colors from the same CSS variables.

| Role | Token / value | Usage |
| --- | --- | --- |
| Outer page | `--color-page` / #E9ECEB | Surround the white app shell |
| Surface | `--color-surface` / #FFFFFF | Panels and controls |
| Mint | `--color-mint` / #EAF2EE | Hero field, agent context, soft emphasis |
| Ink | `--color-ink` / #171B19 | Titles and body text |
| Muted | `--color-muted` / #68736D | Secondary text, still readable |
| Action | `--color-action` / #141815 | One primary action per decision |
| Border | `--color-border` / #DDE3DF | Quiet structure |
| Model | `--scene-model` / #A9B3B0 | Neutral geometry, independent of manufacturing color |
| Success | `--color-success` / #287052 | Confirmed states, paired with words |
| Pending | `--color-warning` / #876322 | Unverified or stale estimates, paired with words |

Typography uses the local sans stack: Inter when installed, Helvetica Neue, Arial, sans-serif. No remote font dependency. Regular and medium weights; strong contrast in size rather than many weights. Hero 38–64 px, workspace title 23–28 px, section title 23–25 px, body 12–14 px, metadata 10–11 px. Uppercase labels are occasional and short. Prices and dimensions use tabular numerals. Tiny labels in the study are supplementary; essential instructions stay at body size.

Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64 px. Control radius 10 px; panel radius 18 px; outer shell 26 px. Prefer borders to shadows. Reserve the light floating shadow for tools over the canvas. Use simple, consistent stroke icons; every icon button needs a text alternative.

## One journey, three densities

1. **Landing:** a large invitation, one starting action, one tangible sample model. A secondary import route supports existing CAD. Space explains the product before controls appear.
2. **Build:** model canvas takes the flexible width; the inspector stays approximately 350 px. View tools float in a narrow rail. Agent conversation, dimensions, and revisions occupy the right panel. The model changes in place as the agent works.
3. **Quote:** preserve the model, camera, and selection; replace the right panel with manufacturing decisions. Preview/upload starts immediately, options remain usable during analysis, and price appears when confirmed. The existing quote’s Model / Material / Review controls are substeps inside this third product phase.

At narrow widths, stack the model above the inspector. Keep viewport controls reachable and visible. Content scrolls naturally rather than squeezing the form into the canvas.

## Interaction language

- Black means an action or selected tool. Mint is a supporting surface, not a blanket success signal.
- The agent is a compact participant, with a small black mark and a clear sentence about its actual work. Avoid a large chatbot overlay covering the part.
- Show concrete progress from events: model ready, material checking, manufacturing ready, shipping pending. Never animate invented percentages or add a delay to fill a step.
- Preserve user choices and camera position between decisions. Label stale prices and provisional options until the matching revision is confirmed.
- The gray preview communicates shape, not the selected physical finish. State this when quoting.
- Respect reduced motion; allow immediate manual control. Keyboard focus is visible. Status includes text, not color alone.

## Implementation map

- `web/theme.css`: reusable tokens and base components.
- `web/style.css`: functional quoting layout using those tokens.
- `web/theme.html`, `web/theme-preview.css`, `web/theme-preview.js`: reviewable three-stage design study. The generated bracket is local sample geometry; the study never creates a provider session.
- `web/viewer.js`: shared renderer, including token-driven scene colors.

The product name is the existing working name. This establishes a reusable visual direction; agent CAD generation and the final checkout are separate implementation work.
