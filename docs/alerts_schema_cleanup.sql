begin;

update public.alerts
set
    symbol = coalesce(nullif(trim(symbol), ''), nullif(trim(ticker), '')),
    threshold = coalesce(threshold, target_price),
    updated_at = coalesce(updated_at, now())
where
    symbol is null
    or trim(symbol) = ''
    or threshold is null
    or updated_at is null;

alter table public.alerts
    alter column symbol set not null;

alter table public.alerts
    alter column threshold set not null;

alter table public.alerts
    alter column ticker drop not null;

alter table public.alerts
    alter column target_price drop not null;

alter table public.alerts
    drop column if exists ticker,
    drop column if exists target_price;

commit;
