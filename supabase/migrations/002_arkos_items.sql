-- ============================================
-- 002: arkos_items — tabla central
-- Tareas, notas, recordatorios, ideas, decisiones, follow-ups
-- ============================================

create table if not exists arkos_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  title text not null,
  description text,

  item_type text not null check (
    item_type in ('task','note','reminder','calendar_event','decision','idea','follow_up')
  ),

  area text default 'general',
  project text,
  category text,

  status text default 'pending' check (
    status in ('pending','done','cancelled','waiting','archived')
  ),

  priority text default 'medium' check (
    priority in ('low','medium','high','urgent')
  ),

  due_date timestamptz,
  remind_at timestamptz,
  reminded boolean default false,

  assigned_to text,        -- persona responsable si no es Jona
  depends_on uuid,         -- referencia a otro item

  source text default 'whatsapp' check (
    source in ('whatsapp','manual','calendar','email','system','dashboard')
  ),

  raw_input text,
  transcription text,

  metadata jsonb default '{}'::jsonb,

  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Indices para queries frecuentes
create index idx_items_user_status on arkos_items(user_id, status);
create index idx_items_user_type on arkos_items(user_id, item_type);
create index idx_items_due_date on arkos_items(due_date) where status = 'pending';
create index idx_items_remind_at on arkos_items(remind_at) where reminded = false;
create index idx_items_area on arkos_items(area);
create index idx_items_project on arkos_items(project) where project is not null;

-- Trigger updated_at
create trigger arkos_items_updated_at
  before update on arkos_items
  for each row
  execute function update_updated_at_column();
