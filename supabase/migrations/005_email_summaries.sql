-- ============================================
-- 005: arkos_email_summaries (Fase 6)
-- ============================================

create table if not exists arkos_email_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  email_id text,
  thread_id text,

  sender text,
  recipients text[],
  subject text,

  summary text,
  importance text check (importance in ('low','medium','high','critical')),
  area text,
  project text,

  suggested_action text,
  requires_response boolean default false,
  deadline timestamptz,

  raw_metadata jsonb default '{}'::jsonb,

  created_at timestamptz default now()
);

create index idx_email_summaries_importance on arkos_email_summaries(user_id, importance);
create index idx_email_summaries_requires_response on arkos_email_summaries(requires_response) where requires_response = true;
