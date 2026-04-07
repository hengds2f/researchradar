-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Create a table to store global papers
create table if not exists public.papers (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  filename text not null,
  chunk_types text[] default '{}',
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Create a table to store categorized chunks alongside their embeddings
create table if not exists public.paper_chunks (
  id uuid primary key default gen_random_uuid(),
  paper_id uuid references public.papers(id) on delete cascade not null,
  section_type text not null, -- abstract, methods, results, discussion
  content text not null,
  embedding vector(1536) -- OpenAI text-embedding-3-small uses 1536 dims
);

-- Function to handle targeted cosine similarity retrieval using specific section metadata
create or replace function match_chunks (
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  valid_sections text[]
)
returns table (
  id uuid,
  paper_id uuid,
  section_type text,
  content text,
  similarity float
)
language sql stable
as $$
  select
    paper_chunks.id,
    paper_chunks.paper_id,
    paper_chunks.section_type,
    paper_chunks.content,
    1 - (paper_chunks.embedding <=> query_embedding) as similarity
  from paper_chunks
  where paper_chunks.section_type = ANY(valid_sections)
    and 1 - (paper_chunks.embedding <=> query_embedding) > match_threshold
  order by paper_chunks.embedding <=> query_embedding
  limit match_count;
$$;
