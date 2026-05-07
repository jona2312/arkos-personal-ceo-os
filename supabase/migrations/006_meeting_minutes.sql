-- ============================================
-- 006: arkos_meeting_minutes (Fase 6)
-- ============================================

create table if not exists arkos_meeting_minutes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  title text not null,
  meeting_date timestamptz default now(),

  participants text[],
  summary text,

  decisions jsonb default '[]'::jsonb,
  action_items jsonb default '[]'::jsonb,
  risks jsonb default '[]'::jsonb,
  next_steps jsonb default '[]'::jsonb,

  source text default 'whatsapp',
  raw_transcript text,

  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create trigger arkos_meeting_minutes_updated_at
  before update on arkos_meeting_minutes
  for each row
  execute function update_updated_at_column();
