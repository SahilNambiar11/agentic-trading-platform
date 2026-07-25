from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.services.job_store import delete_expired_jobs


def main() -> int:
    with SessionLocal() as session:
        deleted = delete_expired_jobs(session, now=datetime.now(UTC))
    print(f"Deleted {deleted} expired preview jobs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
