# Supabase cutover status

Code-side cutover is complete. In forced container mode, the app now uses
Supabase for all durable operational state and refuses to start if the required
Supabase configuration is absent.

External verification is still pending. General Supabase DNS works on this
machine, but the project hostname currently configured in
`supabase_config.txt` does not resolve. This normally means the project URL is
stale, mistyped, paused or deleted. Restore the project or replace the local
configuration with the current project URL before production deployment:

1. Run `supabase/migration_container_readiness.sql` in the existing Supabase
   project (or the full `supabase/schema.sql` for a new project).
2. Run `python migrate_to_supabase.py --check`.
3. Ensure the intended teacher account exists with
   `python migrate_to_supabase.py --users`.
4. Run `python migrate_to_supabase.py --data --owner YOUR_USERNAME` once and
   review its counts.
5. Start the container and confirm `/api/ready` returns HTTP 200.

Local data files remain excluded from every container and deployment package.
Do not work around a failed migration by copying them into the image.
