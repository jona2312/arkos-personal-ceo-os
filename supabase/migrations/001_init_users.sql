-- ============================================
-- 001: Users table
-- ARKOS Personal CEO OS
-- ============================================

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  phone text unique,
  email text,
  role text default 'owner',
  timezone text default 'America/Argentina/Buenos_Aires',
  preferences jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Trigger para updated_at
create or replace function update_updated_at_column()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger users_updated_at
  before update on users
  for each row
  execute function update_updated_at_column();

-- Seed: Jona como owner
insert into users (name, phone, email, role, timezone)
values (
  'Jona Romero',
  '5491100000000',  -- Reemplazar con numero real
  'jonabrewing@gmail.com',
  'owner',
  'America/Argentina/Buenos_Aires'
) on conflict (phone) do nothing;
