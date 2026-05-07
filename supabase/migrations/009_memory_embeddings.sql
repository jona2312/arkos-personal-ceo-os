-- ============================================
-- 009: arkos_memory_embeddings — memoria semantica
-- Requiere extension pgvector habilitada en Supabase
-- ============================================

create extension if not exists vector;

create table if not exists arkos_memory_embeddings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  source_table text,       -- 'arkos_items', 'arkos_messages', 'arkos_meeting_minutes', etc.
  source_id uuid,          -- ID del registro original

  content text not null,   -- texto original
  summary text,            -- resumen corto para contexto rapido
  area text,
  project text,
  memory_type text,        -- 'conversation', 'task', 'decision', 'meeting', 'expense'

  embedding vector(1536),  -- OpenAI text-embedding-3-small = 1536 dims

  metadata jsonb default '{}'::jsonb,

  created_at timestamptz default now()
);

-- Indice HNSW para busqueda semantica rapida
create index idx_memory_embedding_hnsw on arkos_memory_embeddings
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- Indice por usuario
create index idx_memory_user on arkos_memory_embeddings(user_id);

-- Funcion para buscar memoria semantica
create or replace function search_memory(
  query_embedding vector(1536),
  match_threshold float default 0.7,
  match_count int default 5,
  p_user_id uuid default null
)
returns table (
  id uuid,
  content text,
  summary text,
  area text,
  project text,
  memory_type text,
  similarity float,
  created_at timestamptz
)
language plpgsql
as $$
begin
  return query
  select
    m.id,
    m.content,
    m.summary,
    m.area,
    m.project,
    m.memory_type,
    1 - (m.embedding <=> query_embedding) as similarity,
    m.created_at
  from arkos_memory_embeddings m
  where
    (p_user_id is null or m.user_id = p_user_id)
    and 1 - (m.embedding <=> query_embedding) > match_threshold
  order by m.embedding <=> query_embedding
  limit match_count;
end;
$$;
