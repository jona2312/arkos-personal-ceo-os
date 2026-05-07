-- ============================================
-- 003: arkos_messages — historial de conversacion
-- ============================================

create table if not exists arkos_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade not null,

  direction text not null check (direction in ('inbound', 'outbound')),
  channel text default 'whatsapp',
  message_type text check (message_type in ('text','audio','image','document','system')),

  -- WhatsApp Cloud API identifiers
  external_message_id text,
  from_phone text,
  to_phone text,

  -- Content
  text_content text,
  media_url text,
  media_id text,           -- WhatsApp media ID para descargar
  transcription text,

  -- Processing
  intent text,
  department text,
  parsed_json jsonb default '{}'::jsonb,

  -- Tracking
  processed boolean default false,
  processing_error text,

  created_at timestamptz default now()
);

-- Indices
create index idx_messages_user_created on arkos_messages(user_id, created_at desc);
create index idx_messages_external_id on arkos_messages(external_message_id) where external_message_id is not null;
create index idx_messages_unprocessed on arkos_messages(processed) where processed = false;
