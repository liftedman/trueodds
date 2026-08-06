-- Supabase schema for Markets-mode paper trading.
-- Run this once in your Supabase project: SQL Editor -> paste -> Run.
--
-- WHY THIS LIVES IN SUPABASE AND NOT IN data/markets.db
--
-- A paper-trading record is only evidence if it is written BEFORE the outcome is
-- known and never touched afterwards. That means the store has to outlive the
-- process that writes it. data/markets.db cannot do that job here: it is ~98MB
-- so it is gitignored (GitHub blocks >100MB), which means the scheduled cloud
-- job rebuilds it from scratch every run and throws it away. Predictions logged
-- there would evaporate.
--
-- Keeping them here has a second benefit: local runs and cloud runs write to the
-- SAME record, so running `paper` by hand on your laptop contributes to the same
-- forward test rather than starting a private one.
--
-- The rows are tiny (one per instrument per timeframe per run), so this stays
-- small for years.

create table if not exists paper_predictions (
    id            bigserial primary key,

    symbol        text        not null,
    timeframe     text        not null,          -- '5m' / '15m' / '1h' / '1d'
    horizon       int         not null,          -- bars ahead (1)

    -- Open time of the last CLOSED bar used. This is the information cutoff:
    -- the model saw nothing after it.
    made_at_ts    bigint      not null,
    -- Open time of the bar whose close settles the prediction.
    target_ts     bigint      not null,

    ref_close     double precision not null,     -- close at the cutoff
    p_up          double precision not null,     -- P(settle close > ref_close)
    model         text        not null,          -- version tag

    -- Filled in later by `paper --resolve`. NULL while pending.
    settle_close  double precision,
    actual_up     boolean,

    logged_at     timestamptz not null default now(),
    resolved_at   timestamptz,

    -- Makes logging idempotent: re-running for the same bar updates rather than
    -- duplicating, so a retried job cannot inflate the sample.
    unique (symbol, timeframe, horizon, made_at_ts, model)
);

create index if not exists idx_paper_pending
    on paper_predictions (actual_up, target_ts);
create index if not exists idx_paper_symbol
    on paper_predictions (symbol, timeframe);

-- The app reads with the anon key, so allow public SELECT only.
-- Writes happen with the service-role key, which bypasses RLS.
alter table paper_predictions enable row level security;

drop policy if exists "public read paper_predictions" on paper_predictions;
create policy "public read paper_predictions" on paper_predictions
    for select using (true);
