// Design system for generative-UI blocks. One visual language for every component:
// soft layered shadows, 16-18px radii, tenant-colour accents, purposeful motion
// (all of it switched off under prefers-reduced-motion).
export const blockStyles = (c: string) => `
  /* ===== Generative UI blocks ===== */
  .zk-block, .zk-skel, .zk-answer, .zk-progress-strip {
    --zk-accent: ${c};
    --zk-accent-soft: ${c}14;
    --zk-accent-mid: ${c}33;
    --zk-accent-dark: color-mix(in srgb, ${c} 78%, #0b1020);
    --zk-ink: #0f172a;
    --zk-ink-2: #334155;
    --zk-muted: #64748b;
    --zk-faint: #94a3b8;
    --zk-line: #e2e8f0;
    --zk-bg: #f8fafc;
    --zk-ok: #16a34a;
    --zk-warn: #d97706;
    --zk-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 28px -12px rgba(15, 23, 42, 0.14);
    --zk-ease: cubic-bezier(0.22, 1, 0.36, 1);
  }

  @keyframes zk-rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
  @keyframes zk-pop { 0% { transform: scale(0.4); opacity: 0; } 70% { transform: scale(1.15); } 100% { transform: scale(1); opacity: 1; } }
  @keyframes zk-shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
  @keyframes zk-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.8); } }

  .zk-block {
    margin-top: 10px; padding: 16px; background: #fff; color: var(--zk-ink);
    border: 1px solid var(--zk-line); border-radius: 18px; box-shadow: var(--zk-shadow);
    animation: zk-rise 0.35s var(--zk-ease) both;
  }
  .zk-block--quick_chips { padding: 0; border: 0; background: transparent; box-shadow: none; }
  .zk-block--locked { opacity: 0.72; }
  .zk-block__header { margin-bottom: 12px; }
  .zk-block__title { margin: 0; font-size: 15px; font-weight: 650; letter-spacing: -0.01em; color: var(--zk-ink); }
  .zk-block__subtitle { margin: 3px 0 0; font-size: 12.5px; color: var(--zk-muted); }
  .zk-block__changed { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; padding: 7px 10px; font-size: 12px; color: var(--zk-accent-dark); background: var(--zk-accent-soft); border-radius: 10px; }
  .zk-block__fallback { margin-top: 6px; font-size: 13px; color: var(--zk-ink-2); }
  .zk-block__chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .zk-block__sources { margin-top: 12px; padding-top: 10px; border-top: 1px solid #f1f5f9; font-size: 11px; color: var(--zk-faint); }
  .zk-block button:focus-visible, .zk-block input:focus-visible, .zk-block label:focus-within { outline: 2px solid var(--zk-accent); outline-offset: 2px; }

  .zk-block__cta {
    width: 100%; margin-top: 14px; padding: 12px 16px; border: 0; border-radius: 12px; cursor: pointer;
    font: inherit; font-size: 14px; font-weight: 600; color: #fff;
    background: var(--zk-accent); background: linear-gradient(135deg, var(--zk-accent), var(--zk-accent-dark));
    box-shadow: 0 6px 16px -6px ${c}99; transition: transform 0.15s var(--zk-ease), box-shadow 0.15s, opacity 0.15s;
  }
  .zk-block__cta:not(:disabled):hover { transform: translateY(-1px); box-shadow: 0 10px 22px -8px ${c}aa; }
  .zk-block__cta:not(:disabled):active { transform: translateY(0) scale(0.99); }
  .zk-block__cta:disabled { opacity: 0.4; cursor: not-allowed; box-shadow: none; }
  .zk-block__cta--ghost { color: var(--zk-accent-dark); background: var(--zk-accent-soft); box-shadow: none; }
  .zk-block__cta--ghost:not(:disabled):hover { box-shadow: none; background: var(--zk-accent-mid); }

  /* ---- answered summary (collapsed card) ---- */
  .zk-answer { display: flex; align-items: center; gap: 10px; margin-top: 10px; padding: 10px 12px; background: var(--zk-bg); border: 1px solid var(--zk-line); border-radius: 14px; animation: zk-rise 0.3s var(--zk-ease) both; }
  .zk-answer__tick { flex: none; width: 22px; height: 22px; display: grid; place-items: center; color: #fff; background: var(--zk-ok); border-radius: 50%; animation: zk-pop 0.35s var(--zk-ease) both; }
  .zk-answer__text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .zk-answer__q { font-size: 11px; color: var(--zk-muted); }
  .zk-answer__a { font-size: 13.5px; font-weight: 600; color: var(--zk-ink); overflow-wrap: anywhere; }
  .zk-answer__edit { flex: none; padding: 6px 10px; border: 0; border-radius: 8px; font: inherit; font-size: 12px; font-weight: 600; color: var(--zk-accent-dark); background: transparent; cursor: pointer; }
  .zk-answer__edit:hover:not(:disabled) { background: var(--zk-accent-soft); }
  .zk-answer__edit:disabled { opacity: 0.4; cursor: default; }

  /* ---- skeleton while a component is being built ---- */
  .zk-skel { margin-top: 10px; padding: 16px; background: #fff; border: 1px solid var(--zk-line); border-radius: 18px; box-shadow: var(--zk-shadow); animation: zk-rise 0.3s var(--zk-ease) both; }
  .zk-skel__label { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-size: 12.5px; color: var(--zk-muted); }
  .zk-skel__dot { width: 8px; height: 8px; background: var(--zk-accent); border-radius: 50%; animation: zk-pulse 1.1s ease-in-out infinite; }
  .zk-skel__row { display: flex; align-items: center; gap: 10px; margin: 12px 0; }
  .zk-skel__bar, .zk-skel__circle, .zk-skel__box { background: linear-gradient(90deg, #eef2f7 25%, #f8fafc 50%, #eef2f7 75%); background-size: 200% 100%; animation: zk-shimmer 1.3s linear infinite; }
  .zk-skel__bar { flex: 1; height: 12px; border-radius: 6px; }
  .zk-skel__circle { flex: none; width: 28px; height: 28px; border-radius: 50%; }
  .zk-skel__box { flex: none; width: 18px; height: 18px; border-radius: 5px; }

  /* ---- profile progress strip ---- */
  .zk-progress-strip { box-sizing: border-box; width: 100%; max-width: 720px; margin: 0 auto; padding: 10px 20px 8px; }
  .zk-progress-strip__row { display: flex; justify-content: space-between; font-size: 11px; font-weight: 600; letter-spacing: 0.02em; color: var(--zk-muted); }
  .zk-progress-strip__bar { height: 4px; margin-top: 5px; background: var(--zk-line); border-radius: 2px; overflow: hidden; }
  .zk-progress-strip__bar div { height: 100%; background: linear-gradient(90deg, var(--zk-accent), var(--zk-accent-dark)); border-radius: 2px; transition: width 0.6s var(--zk-ease); }

  /* ---- assistant presence (education tenants) ---- */
  .zk-message--rich.zk-message-assistant { position: relative; width: 100%; box-sizing: border-box; padding-left: 42px; }
  .zk-message--rich > .zk-block, .zk-message--rich > .zk-skel, .zk-message--rich > .zk-answer { width: 100%; max-width: 520px; box-sizing: border-box; }
  .zk-message--rich.zk-message-assistant::before {
    content: '✦'; position: absolute; left: 0; top: 0; width: 30px; height: 30px; display: grid; place-items: center;
    font-size: 14px; color: #fff; border-radius: 50%;
    background: ${c}; background: linear-gradient(135deg, ${c}, color-mix(in srgb, ${c} 70%, #0b1020));
    box-shadow: 0 4px 10px -3px ${c}88;
  }

  /* ---- choice cards ---- */
  .zk-choice-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 10px; }
  .zk-choice { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; min-height: 92px; padding: 14px 8px; background: #fff; border: 1.5px solid var(--zk-line); border-radius: 16px; font: inherit; cursor: pointer; animation: zk-rise 0.35s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 45ms); transition: transform 0.18s var(--zk-ease), border-color 0.15s, background 0.15s, box-shadow 0.18s; }
  .zk-choice:not(:disabled):hover { transform: translateY(-2px); border-color: var(--zk-accent-mid); box-shadow: 0 10px 22px -12px ${c}88; }
  .zk-choice:not(:disabled):active { transform: scale(0.97); }
  .zk-choice:disabled { cursor: default; }
  .zk-choice--on { border-color: var(--zk-accent); background: var(--zk-accent-soft); box-shadow: 0 0 0 3px var(--zk-accent-soft); }
  .zk-choice__check { position: absolute; top: 7px; right: 7px; width: 20px; height: 20px; display: grid; place-items: center; color: #fff; background: var(--zk-accent); border-radius: 50%; animation: zk-pop 0.3s var(--zk-ease) both; }
  .zk-choice--text { min-height: 56px; padding: 10px 8px; }
  .zk-choice__icon { font-size: 30px; line-height: 1; }
  .zk-choice__label { font-size: 13px; font-weight: 600; color: var(--zk-ink); text-align: center; }
  .zk-choice__hint { font-size: 11px; color: var(--zk-muted); text-align: center; }

  /* ---- sliders ---- */
  .zk-slider__value { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; color: var(--zk-ink); font-variant-numeric: tabular-nums; }
  .zk-slider__value span { font-size: 12.5px; font-weight: 500; letter-spacing: 0; color: var(--zk-muted); }
  .zk-range { -webkit-appearance: none; appearance: none; display: block; width: 100%; height: 8px; margin: 14px 0 6px; border-radius: 999px; outline: none; cursor: pointer;
    background: linear-gradient(to right, var(--zk-accent) var(--fill, 50%), var(--zk-line) var(--fill, 50%)); }
  .zk-range::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 24px; height: 24px; background: #fff; border: 3px solid var(--zk-accent); border-radius: 50%; box-shadow: 0 3px 10px rgba(15, 23, 42, 0.22); cursor: grab; transition: transform 0.12s var(--zk-ease); }
  .zk-range::-moz-range-thumb { width: 18px; height: 18px; background: #fff; border: 3px solid var(--zk-accent); border-radius: 50%; box-shadow: 0 3px 10px rgba(15, 23, 42, 0.22); cursor: grab; }
  .zk-range:active::-webkit-slider-thumb { transform: scale(1.15); cursor: grabbing; }
  .zk-range:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 5px var(--zk-accent-mid); }
  .zk-range:disabled { cursor: default; opacity: 0.6; }
  .zk-slider__scale { display: flex; justify-content: space-between; font-size: 11px; color: var(--zk-faint); }

  /* ---- match cards ---- */
  .zk-match-list { display: flex; flex-direction: column; gap: 10px; }
  .zk-match { display: flex; gap: 14px; padding: 14px; background: #fff; border: 1px solid var(--zk-line); border-radius: 16px; animation: zk-rise 0.4s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 70ms); transition: border-color 0.15s, box-shadow 0.18s, transform 0.18s var(--zk-ease); }
  .zk-match--strong { border-color: var(--zk-accent-mid); background: linear-gradient(180deg, var(--zk-accent-soft), #fff 70%); }
  .zk-match:hover { transform: translateY(-1px); box-shadow: 0 10px 22px -14px rgba(15, 23, 42, 0.3); }
  .zk-match__body { flex: 1; min-width: 0; }
  .zk-match__head { display: flex; align-items: center; gap: 8px; }
  .zk-match__flag { font-size: 20px; line-height: 1; }
  .zk-match__label { flex: 1; font-size: 15px; font-weight: 650; letter-spacing: -0.01em; color: var(--zk-ink); }
  .zk-match__tier { padding: 2px 9px; font-size: 11px; font-weight: 700; letter-spacing: 0.02em; white-space: nowrap; border-radius: 999px; }
  .zk-match__tier--strong { color: #fff; background: var(--zk-ok); }
  .zk-match__tier--good { color: var(--zk-accent-dark); background: var(--zk-accent-soft); }
  .zk-match__tier--possible { color: #92400e; background: #fef3c7; }
  .zk-match__tier--needs_review { color: var(--zk-ink-2); background: #f1f5f9; border: 1px solid var(--zk-line); }
  .zk-match__reasons { display: flex; flex-direction: column; gap: 4px; margin: 8px 0 0; padding: 0; list-style: none; }
  .zk-match__reasons li { display: flex; gap: 6px; font-size: 12.5px; line-height: 1.4; color: var(--zk-ink-2); }
  .zk-match__mark { flex: none; width: 16px; text-align: center; font-weight: 700; }
  .zk-match__reason--pass .zk-match__mark { color: var(--zk-ok); }
  .zk-match__reason--partial .zk-match__mark { color: var(--zk-warn); }
  .zk-match__reason--fail .zk-match__mark { color: #b91c1c; }
  .zk-match__reason--info .zk-match__mark { color: var(--zk-muted); font-style: italic; }
  .zk-match__more { margin-top: 10px; padding: 6px 12px; border: 0; border-radius: 999px; font: inherit; font-size: 12px; font-weight: 600; color: var(--zk-accent-dark); background: var(--zk-accent-soft); cursor: pointer; transition: background 0.15s; }
  .zk-match__more:hover { background: var(--zk-accent-mid); }

  /* ---- info / profile ---- */
  .zk-info__head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 15px; font-weight: 650; color: var(--zk-ink); }
  .zk-info__rows { margin: 0; }
  .zk-info__row { display: flex; justify-content: space-between; gap: 14px; padding: 9px 0; font-size: 13px; border-top: 1px solid #f1f5f9; }
  .zk-info__row:first-child { border-top: 0; }
  .zk-info__row dt { color: var(--zk-muted); }
  .zk-info__row dd { margin: 0; font-weight: 600; color: var(--zk-ink); text-align: right; }
  .zk-info__missing { margin-top: 10px; padding: 8px 10px; font-size: 12px; color: var(--zk-muted); background: var(--zk-bg); border-radius: 10px; }

  /* ---- comparison ---- */
  .zk-compare { overflow-x: auto; margin: 0 -4px; padding: 0 4px; }
  .zk-compare table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12.5px; }
  .zk-compare th, .zk-compare td { padding: 10px 8px; text-align: left; border-top: 1px solid #f1f5f9; }
  .zk-compare thead th { padding-bottom: 12px; border-top: 0; font-size: 13px; font-weight: 650; color: var(--zk-ink); }
  .zk-compare thead th:not(:first-child) { text-align: center; }
  .zk-compare tbody th { font-weight: 500; color: var(--zk-muted); white-space: nowrap; }
  .zk-compare td { font-weight: 600; color: var(--zk-ink); text-align: center; }
  .zk-compare tbody tr:nth-child(odd) td, .zk-compare tbody tr:nth-child(odd) th { background: var(--zk-bg); }
  .zk-compare tbody tr:nth-child(odd) th { border-radius: 10px 0 0 10px; }
  .zk-compare tbody tr:nth-child(odd) td:last-child { border-radius: 0 10px 10px 0; }

  /* ---- eligibility ---- */
  .zk-elig__top { display: flex; align-items: center; gap: 12px; }
  .zk-elig__badge { flex: none; width: 30px; height: 30px; display: grid; place-items: center; font-weight: 700; color: #fff; border-radius: 50%; }
  .zk-elig__badge--ok { background: var(--zk-ok); }
  .zk-elig__badge--some { background: var(--zk-warn); }
  .zk-elig__verdict { font-size: 14px; font-weight: 600; color: var(--zk-ink); }
  .zk-elig__checks { display: flex; flex-direction: column; gap: 10px; margin: 14px 0 0; padding: 0; list-style: none; }
  .zk-elig__checks li { display: flex; gap: 10px; font-size: 12.5px; animation: zk-rise 0.35s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 70ms); }
  .zk-elig__icon { flex: none; width: 20px; height: 20px; display: grid; place-items: center; font-size: 11px; font-weight: 700; color: #fff; border-radius: 50%; }
  .zk-elig__ok .zk-elig__icon { background: var(--zk-ok); }
  .zk-elig__no .zk-elig__icon { background: var(--zk-warn); }
  .zk-elig__checks strong { display: block; color: var(--zk-ink); }
  .zk-elig__checks em { font-style: normal; color: var(--zk-muted); }

  /* ---- progress (stepper / checklist) ---- */
  .zk-progress { height: 6px; background: var(--zk-line); border-radius: 3px; overflow: hidden; }
  .zk-progress div { height: 100%; background: linear-gradient(90deg, var(--zk-accent), var(--zk-accent-dark)); border-radius: 3px; transition: width 0.4s var(--zk-ease); }
  .zk-progress__label { margin: 6px 0 12px; font-size: 11.5px; font-weight: 600; color: var(--zk-muted); }
  .zk-celebrate { margin-top: 12px; padding: 10px 12px; display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--zk-ok); background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; animation: zk-pop 0.4s var(--zk-ease) both; }

  /* ---- stepper ---- */
  .zk-stepper__list { margin: 0; padding: 0; list-style: none; }
  .zk-step { position: relative; padding-bottom: 4px; animation: zk-rise 0.35s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 60ms); }
  .zk-step:not(:last-child)::after { content: ''; position: absolute; left: 15px; top: 36px; bottom: 0; width: 2px; background: var(--zk-line); transition: background 0.3s; }
  .zk-step--done:not(:last-child)::after { background: var(--zk-accent); }
  .zk-step__head { display: flex; align-items: center; gap: 12px; width: 100%; padding: 4px 6px 4px 0; border: 0; background: none; font: inherit; text-align: left; cursor: pointer; border-radius: 10px; }
  .zk-step__num { flex: none; width: 32px; height: 32px; display: grid; place-items: center; font-size: 13px; font-weight: 700; color: var(--zk-muted); background: #fff; border: 2px solid var(--zk-line); border-radius: 50%; transition: all 0.25s var(--zk-ease); }
  .zk-step--open .zk-step__num { color: var(--zk-accent-dark); border-color: var(--zk-accent); background: var(--zk-accent-soft); }
  .zk-step--done .zk-step__num { color: #fff; background: var(--zk-accent); border-color: var(--zk-accent); }
  .zk-step__title { flex: 1; font-size: 14px; font-weight: 600; color: var(--zk-ink); }
  .zk-step--done .zk-step__title { color: var(--zk-muted); }
  .zk-step__chevron { color: var(--zk-faint); font-size: 14px; transition: transform 0.2s; }
  .zk-step--open .zk-step__chevron { transform: rotate(90deg); }
  .zk-step__panel { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.28s var(--zk-ease); }
  .zk-step--open .zk-step__panel { grid-template-rows: 1fr; }
  .zk-step__panel > div { overflow: hidden; }
  .zk-step__body { margin: 4px 0 10px 44px; padding: 10px 12px; font-size: 13px; line-height: 1.5; color: var(--zk-ink-2); background: var(--zk-bg); border-radius: 12px; }
  .zk-step__body p { margin: 0 0 8px; }
  .zk-step__body p:last-of-type { margin-bottom: 0; }
  .zk-step__done { margin-top: 8px; padding: 6px 12px; border: 0; border-radius: 999px; font: inherit; font-size: 12px; font-weight: 600; color: var(--zk-accent-dark); background: var(--zk-accent-soft); cursor: pointer; transition: background 0.15s; }
  .zk-step__done:hover { background: var(--zk-accent-mid); }

  /* ---- accordion ---- */
  .zk-accordion { display: flex; flex-direction: column; gap: 8px; }
  .zk-acc { background: #fff; border: 1px solid var(--zk-line); border-radius: 14px; overflow: hidden; animation: zk-rise 0.35s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 55ms); transition: border-color 0.15s, box-shadow 0.2s; }
  .zk-acc:hover { border-color: var(--zk-accent-mid); }
  .zk-acc--open { border-color: var(--zk-accent-mid); box-shadow: 0 10px 22px -16px ${c}99; }
  .zk-acc__head { display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 14px; border: 0; background: none; font: inherit; text-align: left; cursor: pointer; }
  .zk-acc__text { flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .zk-acc__title { font-size: 14px; font-weight: 600; color: var(--zk-ink); }
  .zk-acc__summary { font-size: 12px; color: var(--zk-muted); }
  .zk-acc__chevron { flex: none; width: 24px; height: 24px; display: grid; place-items: center; font-size: 15px; color: var(--zk-accent-dark); background: var(--zk-accent-soft); border-radius: 50%; transition: transform 0.25s var(--zk-ease), background 0.15s; }
  .zk-acc--open .zk-acc__chevron { transform: rotate(45deg); background: var(--zk-accent-mid); }
  .zk-acc__panel { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.28s var(--zk-ease); }
  .zk-acc--open .zk-acc__panel { grid-template-rows: 1fr; }
  .zk-acc__panel > div { overflow: hidden; }
  .zk-acc__body { padding: 0 14px 14px; font-size: 13px; line-height: 1.55; color: var(--zk-ink-2); }

  /* ---- checklist ---- */
  .zk-checklist__list { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
  .zk-check { display: flex; align-items: flex-start; gap: 12px; padding: 11px 12px; background: #fff; border: 1.5px solid var(--zk-line); border-radius: 14px; cursor: pointer; animation: zk-rise 0.35s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 50ms); transition: background 0.15s, border-color 0.15s, transform 0.12s var(--zk-ease); }
  .zk-check:hover { border-color: var(--zk-accent-mid); }
  .zk-check:active { transform: scale(0.99); }
  .zk-check--on { background: var(--zk-accent-soft); border-color: var(--zk-accent-mid); }
  .zk-check input { position: absolute; opacity: 0; pointer-events: none; }
  .zk-check__box { flex: none; width: 20px; height: 20px; margin-top: 1px; display: grid; place-items: center; color: #fff; border: 2px solid #cbd5e1; border-radius: 6px; transition: all 0.2s var(--zk-ease); }
  .zk-check--on .zk-check__box { background: var(--zk-accent); border-color: var(--zk-accent); animation: zk-pop 0.3s var(--zk-ease); }
  .zk-check input:focus-visible + .zk-check__box { box-shadow: 0 0 0 4px var(--zk-accent-mid); }
  .zk-check__text { display: flex; flex-direction: column; gap: 2px; }
  .zk-check__label { font-size: 13.5px; font-weight: 600; color: var(--zk-ink); transition: color 0.2s; }
  .zk-check--on .zk-check__label { color: var(--zk-muted); text-decoration: line-through; text-decoration-color: var(--zk-faint); }
  .zk-check__note { font-size: 12px; color: var(--zk-muted); }

  /* ---- timeline ---- */
  .zk-timeline { position: relative; margin: 0; padding: 0 0 0 22px; list-style: none; display: flex; flex-direction: column; gap: 6px; }
  .zk-timeline::before { content: ''; position: absolute; left: 6px; top: 12px; bottom: 12px; width: 2px; background: linear-gradient(var(--zk-accent-mid), var(--zk-line)); border-radius: 1px; }
  .zk-tl { position: relative; animation: zk-rise 0.35s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 60ms); }
  .zk-tl__dot { position: absolute; left: -22px; top: 13px; width: 14px; height: 14px; background: #fff; border: 3px solid var(--zk-accent); border-radius: 50%; transition: background 0.2s, transform 0.2s var(--zk-ease); }
  .zk-tl--open .zk-tl__dot { background: var(--zk-accent); transform: scale(1.15); }
  .zk-tl__head { display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 8px 10px; border: 0; background: none; font: inherit; text-align: left; border-radius: 12px; cursor: pointer; transition: background 0.15s; }
  .zk-tl__head:disabled { cursor: default; }
  .zk-tl__head:not(:disabled):hover { background: var(--zk-accent-soft); }
  .zk-tl__when { font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--zk-accent-dark); }
  .zk-tl__title { font-size: 14px; font-weight: 600; color: var(--zk-ink); }
  .zk-tl__detail { margin: 0 10px 6px; font-size: 12.5px; line-height: 1.5; color: var(--zk-ink-2); }

  /* ---- cost calculator ---- */
  .zk-calc__bar { display: flex; height: 10px; margin-bottom: 14px; overflow: hidden; background: var(--zk-line); border-radius: 999px; }
  .zk-calc__bar div { transition: width 0.35s var(--zk-ease); }
  .zk-calc__bar div:nth-child(1) { background: var(--zk-accent); }
  .zk-calc__bar div:nth-child(2) { background: color-mix(in srgb, ${c} 45%, #fff); }
  .zk-calc__bar div:nth-child(3) { background: color-mix(in srgb, ${c} 22%, #fff); }
  .zk-calc__part { margin-bottom: 12px; }
  .zk-calc__row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: var(--zk-ink-2); }
  .zk-calc__row span { display: flex; align-items: center; gap: 8px; }
  .zk-calc__swatch { width: 10px; height: 10px; border-radius: 3px; }
  .zk-calc__row strong { font-variant-numeric: tabular-nums; color: var(--zk-ink); }
  .zk-calc__total { display: flex; justify-content: space-between; align-items: baseline; margin-top: 14px; padding: 12px 14px; font-size: 13px; color: var(--zk-ink-2); background: linear-gradient(135deg, var(--zk-accent-soft), #fff); border: 1px solid var(--zk-accent-mid); border-radius: 14px; }
  .zk-calc__total strong { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; color: var(--zk-accent-dark); font-variant-numeric: tabular-nums; }
  .zk-calc__note { margin-top: 10px; font-size: 11.5px; color: var(--zk-faint); }

  /* ---- journey tiles ---- */
  .zk-journey { display: flex; flex-direction: column; gap: 10px; }
  .zk-tile { display: flex; align-items: center; gap: 14px; width: 100%; padding: 14px; background: #fff; border: 1.5px solid var(--zk-line); border-radius: 16px; font: inherit; text-align: left; cursor: pointer; animation: zk-rise 0.4s var(--zk-ease) both; animation-delay: calc(var(--i, 0) * 70ms); transition: border-color 0.15s, transform 0.18s var(--zk-ease), box-shadow 0.2s; }
  .zk-tile:not(:disabled):hover { border-color: var(--zk-accent-mid); transform: translateY(-2px); box-shadow: 0 12px 24px -14px ${c}aa; }
  .zk-tile:not(:disabled):active { transform: scale(0.985); }
  .zk-tile:disabled { cursor: default; opacity: 0.7; }
  .zk-tile__icon { flex: none; width: 44px; height: 44px; display: grid; place-items: center; font-size: 22px; background: linear-gradient(135deg, var(--zk-accent-soft), var(--zk-accent-mid)); border-radius: 14px; }
  .zk-tile__text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .zk-tile__title { font-size: 14.5px; font-weight: 650; letter-spacing: -0.01em; color: var(--zk-ink); }
  .zk-tile__desc { font-size: 12.5px; color: var(--zk-muted); }
  .zk-tile__go { flex: none; font-size: 18px; color: var(--zk-accent); transition: transform 0.2s var(--zk-ease); }
  .zk-tile:not(:disabled):hover .zk-tile__go { transform: translateX(4px); }

  /* ---- lead form ---- */
  .zk-leadform { display: flex; flex-direction: column; gap: 12px; }
  .zk-leadform__field { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 600; color: var(--zk-ink-2); }
  .zk-leadform__field input { padding: 11px 12px; font: inherit; font-size: 14px; font-weight: 400; color: var(--zk-ink); background: #fff; border: 1.5px solid var(--zk-line); border-radius: 12px; outline: none; transition: border-color 0.15s, box-shadow 0.15s; }
  .zk-leadform__field input:focus { border-color: var(--zk-accent); box-shadow: 0 0 0 4px var(--zk-accent-soft); }
  .zk-leadform__field input:disabled { background: var(--zk-bg); }
  .zk-leadform__field--bad input { border-color: #f87171; }
  .zk-leadform__err { font-size: 11.5px; font-weight: 500; color: #dc2626; }

  /* ---- mobile ---- */
  .zk-mobile .zk-block { padding: 14px; border-radius: 16px; }
  .zk-mobile .zk-choice-grid { grid-template-columns: repeat(2, 1fr); }
  .zk-mobile .zk-choice, .zk-mobile .zk-tile, .zk-mobile .zk-check, .zk-mobile .zk-acc__head, .zk-mobile .zk-block__cta { min-height: 48px; }
  .zk-mobile .zk-message--rich.zk-message-assistant { padding-left: 38px; }
  /* phones: cards use the full width under the avatar instead of sitting indented beside it */
  .zk-mobile .zk-message--rich > .zk-block, .zk-mobile .zk-message--rich > .zk-skel, .zk-mobile .zk-message--rich > .zk-answer { margin-left: -38px; }

  @media (prefers-reduced-motion: reduce) {
    .zk-block, .zk-skel, .zk-answer, .zk-choice, .zk-match, .zk-step, .zk-acc, .zk-check, .zk-tl, .zk-tile, .zk-elig__checks li,
    .zk-celebrate, .zk-choice__check, .zk-answer__tick, .zk-check--on .zk-check__box { animation: none !important; }
    .zk-skel__bar, .zk-skel__circle, .zk-skel__box, .zk-skel__dot { animation: none !important; }
    .zk-block *, .zk-answer * { transition: none !important; }
  }
`
