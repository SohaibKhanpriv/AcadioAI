#!/bin/sh
# Run migrations then start the app. Use same env as the app (e.g. DATABASE_URL).
set -e
echo "Running database migrations..."
if ! alembic upgrade head; then
    echo "ERROR: Migrations failed. Fix the database and try again."
    exit 1
fi
echo "Migrations complete. Starting application..."
exec "$@"
