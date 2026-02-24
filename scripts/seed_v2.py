from werkzeug.security import generate_password_hash

from config.database import db_session
from db.models import Project, User


if __name__ == "__main__":
    with db_session() as db:
        user = db.query(User).filter(User.email == "demo@example.com").first()
        if not user:
            user = User(email="demo@example.com", password_hash=generate_password_hash("demo1234"), full_name="Demo User")
            db.add(user)
            db.flush()

        project = db.query(Project).filter(Project.user_id == user.id, Project.name == "Projekt demo v2").first()
        if not project:
            db.add(Project(user_id=user.id, name="Projekt demo v2", description="Seeded project", status="draft"))

    print("Seed completed.")
