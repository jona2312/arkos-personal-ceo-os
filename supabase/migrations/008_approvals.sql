-- ============================================
-- 008: arkos_approvals — log de aprobaciones
-- ============================================

create table if not exists arkos_approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  action_type text not null,
  action_payload jsonb not null,
  action_description text,  -- descripcion legible para Jona

  status text default 'pending' check (
    status in ('pending','approved','rejected','expired','executed')
  ),

  confirmation_message text,
  approved_at timestamptz,
  rejected_at timestamptz,
  executed_at timestamptz,
  expires_at timestamptz,   -- si no se aprueba en X tiempo, expira

  created_at timestamptz default now()
);

create index idx_approvals_pending on arkos_approvals(user_id, status) where status = 'pending';
