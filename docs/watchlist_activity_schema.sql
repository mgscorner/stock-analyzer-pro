create table if not exists public.watchlist_activity (
    user_id uuid not null,
    watchlist_name text not null,
    is_visible boolean not null default false,
    last_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, watchlist_name)
);

create index if not exists watchlist_activity_seen_idx
    on public.watchlist_activity (last_seen_at desc);

create index if not exists watchlist_activity_visible_seen_idx
    on public.watchlist_activity (is_visible, last_seen_at desc);
