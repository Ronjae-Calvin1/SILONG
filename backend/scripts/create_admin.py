"""
Creates the FIRST Admin. Run it once, from the backend folder:

    py scripts/create_admin.py

It asks for a name and a password (the password is not shown while you type).
After that, sign in and create other accounts from the app (any Admin can).
It refuses to run when an Admin already exists, and it uses the same
database as the backend (DATABASE_URL, default typhoon.db in this folder).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import accounts, config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401  (makes sure every table is known)


def main() -> int:
    Base.metadata.create_all(bind=engine)  # makes the account tables if this is a new database
    db = SessionLocal()
    try:
        # An older database may still hold accounts with the old roles: they count as Admins once migrated.
        accounts.migrate_roles(db)
        if accounts.has_admin(db):
            print("An Admin already exists. Sign in and create more accounts from the app.")
            return 1

        name = input("Admin name: ").strip()
        password = getpass.getpass(f"Password (at least {config.MIN_PASSWORD_LENGTH} characters): ")
        if password != getpass.getpass("Type the password again: "):
            print("The two passwords do not match. Nothing was created.")
            return 1

        user = accounts.create_first_admin(db, name, password)
        print(f"Done. Admin '{user.name}' was created. You can sign in now.")
        return 0
    except accounts.AccountError as e:
        print(f"Nothing was created: {e.detail}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
