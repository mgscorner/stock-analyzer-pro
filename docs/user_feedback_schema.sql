create table if not exists public.user_feedback (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    feedback_type text not null default 'general',
    message text not null,
    context_watchlist text,
    context_symbol text,
    status text not null default 'new',
    created_at timestamptz not null default now()
);

alter table public.user_feedback enable row level security;

drop policy if exists user_feedback_insert_own on public.user_feedback;
create policy user_feedback_insert_own
    on public.user_feedback
    for insert
    to authenticated
    with check (auth.uid() = user_id);

drop policy if exists user_feedback_select_own on public.user_feedback;
create policy user_feedback_select_own
    on public.user_feedback
    for select
    to authenticated
    using (auth.uid() = user_id);

create index if not exists user_feedback_user_created_idx
    on public.user_feedback (user_id, created_at desc);

create index if not exists user_feedback_status_created_idx
    on public.user_feedback (status, created_at desc);
