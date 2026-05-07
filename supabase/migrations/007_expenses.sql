-- ============================================
-- 007: arkos_expenses (Fase 7)
-- ============================================

create table if not exists arkos_expenses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  title text not null,
  description text,

  amount numeric,
  currency text default 'ARS',

  expense_date date,
  due_date date,

  vendor text,
  category text,
  subcategory text,

  scope text check (scope in ('personal','business')),
  company text,
  project text,

  payment_status text default 'pending' check (
    payment_status in ('pending','paid','cancelled','needs_review')
  ),

  payment_method text,
  receipt_url text,

  source text default 'whatsapp',
  raw_input text,
  extracted_data jsonb default '{}'::jsonb,

  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_expenses_user_status on arkos_expenses(user_id, payment_status);
create index idx_expenses_due_date on arkos_expenses(due_date) where payment_status = 'pending';
create index idx_expenses_scope on arkos_expenses(scope);

create trigger arkos_expenses_updated_at
  before update on arkos_expenses
  for each row
  execute function update_updated_at_column();
