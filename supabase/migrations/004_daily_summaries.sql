-- ============================================
-- 004: arkos_daily_summaries
-- ============================================

create table if not exists arkos_daily_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  summary_date date not null,
  morning_summary text,
  evening_summary text,

  focus_of_day text,
  day_score jsonb default '{}'::jsonb,

  key_tasks jsonb default '[]'::jsonb,
  pending_items jsonb default '[]'::jsonb,
  completed_items jsonb default '[]'::jsonb,
  decisions jsonb default '[]'::jsonb,

  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create unique index idx_daily_summaries_user_date on arkos_daily_summaries(user_id, summary_date);

create trigger arkos_daily_summaries_updated_at
  before update on arkos_daily_summaries
  for each row
  execute function update_updated_at_column();
