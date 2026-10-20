
from database import get_database

with get_database() as connection:
    users = connection.execute(
        "SELECT id, email FROM users ORDER BY id"
    ).fetchall()

for user in users:
    print(f"ID: {user['id']} | Email: {user['email']}")

print(f"\nTotal registered accounts: {len(users)}")
