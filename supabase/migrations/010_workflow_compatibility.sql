-- ============================================
-- 010: Compatibilidad workflows n8n v2
-- Ajustes para que las tablas coincidan con los campos
-- usados por ARKOS_CEO_AGENT y sub-workflows
-- ============================================

-- === arkos_items: agregar campos faltantes ===

-- content: los workflows usan 'content' en vez de 'description'
ALTER TABLE arkos_items ADD COLUMN IF NOT EXISTS content text;
-- migrar datos existentes de description a content
UPDATE arkos_items SET content = description WHERE content IS NULL AND description IS NOT NULL;

-- department: los workflows clasifican por department
ALTER TABLE arkos_items ADD COLUMN IF NOT EXISTS department text;

-- tags: los workflows envian tags como array
ALTER TABLE arkos_items ADD COLUMN IF NOT EXISTS tags text[] DEFAULT '{}';

-- Ampliar item_type para soportar todos los tipos que usan los workflows
ALTER TABLE arkos_items DROP CONSTRAINT IF EXISTS arkos_items_item_type_check;
ALTER TABLE arkos_items ADD CONSTRAINT arkos_items_item_type_check CHECK (
  item_type IN ('task','note','reminder','calendar_event','decision','idea','follow_up','expense','meeting_minute')
);

-- Ampliar status para incluir 'active' (usado por workflows)
ALTER TABLE arkos_items DROP CONSTRAINT IF EXISTS arkos_items_status_check;
ALTER TABLE arkos_items ADD CONSTRAINT arkos_items_status_check CHECK (
  status IN ('pending','active','done','cancelled','waiting','archived')
);

-- Indice por department
CREATE INDEX IF NOT EXISTS idx_items_department ON arkos_items(department) WHERE department IS NOT NULL;

-- === search_memory: funcion de busqueda por texto (Day 1) ===
-- La funcion original requiere vector embedding.
-- Para Day 1 creamos una busqueda por texto simple en arkos_items + arkos_messages.
-- Cuando tengamos embeddings reales, se usa la funcion original.

CREATE OR REPLACE FUNCTION search_memory(
  search_text text,
  p_user_id uuid DEFAULT NULL,
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id uuid,
  item_type text,
  title text,
  content text,
  department text,
  status text,
  due_date timestamptz,
  created_at timestamptz,
  source_table text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  (
    -- Buscar en arkos_items
    SELECT
      i.id,
      i.item_type,
      i.title,
      COALESCE(i.content, i.description) as content,
      i.department,
      i.status,
      i.due_date,
      i.created_at,
      'arkos_items'::text as source_table
    FROM arkos_items i
    WHERE
      (p_user_id IS NULL OR i.user_id = p_user_id)
      AND i.status NOT IN ('cancelled', 'archived')
      AND (
        i.title ILIKE '%' || search_text || '%'
        OR i.content ILIKE '%' || search_text || '%'
        OR i.description ILIKE '%' || search_text || '%'
      )
    ORDER BY i.created_at DESC
    LIMIT match_count
  )
  UNION ALL
  (
    -- Buscar en mensajes recientes
    SELECT
      m.id,
      'message'::text as item_type,
      m.text_content as title,
      m.text_content as content,
      m.department,
      CASE WHEN m.processed THEN 'processed' ELSE 'pending' END as status,
      NULL::timestamptz as due_date,
      m.created_at,
      'arkos_messages'::text as source_table
    FROM arkos_messages m
    WHERE
      (p_user_id IS NULL OR m.user_id = p_user_id)
      AND m.direction = 'inbound'
      AND m.text_content ILIKE '%' || search_text || '%'
    ORDER BY m.created_at DESC
    LIMIT 3
  )
  ORDER BY created_at DESC
  LIMIT match_count;
END;
$$;

-- === Busqueda por fecha (para "que tengo el sabado") ===
CREATE OR REPLACE FUNCTION search_items_by_date(
  p_user_id uuid,
  p_date date
)
RETURNS TABLE (
  id uuid,
  item_type text,
  title text,
  content text,
  department text,
  status text,
  due_date timestamptz,
  remind_at timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    i.id,
    i.item_type,
    i.title,
    COALESCE(i.content, i.description) as content,
    i.department,
    i.status,
    i.due_date,
    i.remind_at
  FROM arkos_items i
  WHERE
    i.user_id = p_user_id
    AND i.status NOT IN ('cancelled', 'archived')
    AND (
      DATE(i.due_date) = p_date
      OR DATE(i.remind_at) = p_date
    )
  ORDER BY i.due_date ASC;
END;
$$;
