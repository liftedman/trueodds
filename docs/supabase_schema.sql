-- Supabase schema for sports-model.
-- Run this once in your Supabase project: SQL Editor → paste → Run.
--
-- One row holds the whole prediction snapshot (ratings, params, fixtures) as
-- JSON — the same structure the web dashboard embeds. The scheduled `push`
-- job upserts id='latest'; the app reads it and computes matchups client-side.

create table if not exists snapshot (
    id          text primary key,
    data        jsonb       not null,
    updated_at  timestamptz not null default now()
);

-- The app reads with the anon key, so allow public SELECT only.
-- Writes happen with the service-role key, which bypasses RLS.
alter table snapshot enable row level security;

drop policy if exists "public read snapshot" on snapshot;
create policy "public read snapshot" on snapshot
    for select using (true);
