# Beirut exercise: presenter walkthrough

Run the isolated launcher from the README and open `/overview`. The normal
presentation is now six numbered steps: **Situation → Forecast → Incident & AI →
Response → Recovery funding → Outcomes**. Hospital reports are a supporting link.
One compact context strip labels the synthetic data and current exercise clock.

## Presentation story

1. **Situation:** 48 simultaneous emergency places are planned across three
   receiving hospitals. Compare the saved incident (28 supported), response (36),
   and later recovery package (48). These are synthetic planned service places,
   not historical casualties or measured lives saved. The current map remains
   separate from saved comparisons. Expand the cause cards only when needed.
2. **Forecast:** inspect seven future days for a receiving hospital. There are 63
   synthetic pre-event days. Advancing to recovery appends synthetic completed
   follow-up days through 10 August, so the 11 August forecast remains available.
   History never contains tomorrow's funded benefits. The closed/unconfirmed
   hospitals can still have unavailable or incomplete estimates; unknown is not zero.
3. **Incident & AI:** the Beirut report and saved impact are ready. Choose
   **Generate recommendations · live AI** to request prioritized actions, reasons,
   prerequisites and supporting evidence. This explicit action uses the configured
   server-side key. Nothing calls the provider automatically. Edited report text
   changes AI input, while the saved comparison stays labeled as the original
   scenario. Follow **Compare the feasible response** to numerical planning.
4. **Response:** review eight monitors proposed from Mount Lebanon to West, its
   protected local capacity, 45-minute route and $800 cost. Expand inputs only to
   calculate another response. Coverage rises to 36, leaving a 12-place gap.
5. **Recovery funding:** read the package and project cards first. Four repaired
   West monitors and four confirmed East nurses cost $10,000, including the
   operating allowance, with effects evaluated on 11 August. The $800 transfer
   is separate. Change the dollar budget or eligible candidates and click
   **Compare funding options** for a new saved calculation. Existing results remain
   labeled while inputs change. Alternatives do not silently replace the canonical
   decisions used by the exercise rehearsal.
6. **Outcomes:** review the two decision cards. **Simulate transfer and receive
   reports** records explicit synthetic review/completion and separate report
   arrivals. **Simulate recovery and review outcomes** advances to recovery and
   retains two comparisons. Switch **Before fresh reports / After fresh reports**
   to see missing evidence versus supported expected capacity. Each hospital's
   expected and reported estimate is visible; source details are expandable.

The old development previews, raw-ID creation forms and manual event editor are
outside the normal Beirut journey. Existing generic screens remain available with
`advanced=1` for detailed development work and alternative proposal decisions.
No actual dispatch, patient matching or spending occurs.

## Resume and repeat

The launcher resumes the existing isolated database and appends only missing
synthetic history. It repairs older 35-day demo files and recovery-stage history
without overwriting reports, daily values, decisions or saved scenarios. Stop the
API and launch with `--fresh` only when you want another complete rehearsal; old
files remain. The compact top strip shows which phase you resumed.

Normal decision approval/completion still changes no inventory. Rehearsal buttons
explicitly simulate both actions and separate report arrivals. Forecasts use daily
history, not current resource updates. User browser rehearsal remains the final
presentation check; no frontend tests/builds/browser automation were run.
