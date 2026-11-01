
import getpass
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Membership, Tenant, User
from app.security import hash_password


def main():
    email = input("Correo del administrador: ").strip().lower()
    organization = input("Nombre de la organización: ").strip()

    password = getpass.getpass("Contraseña: ")
    confirmation = getpass.getpass("Confirmar contraseña: ")

    if not email or not organization:
        sys.exit("El correo y la organización son obligatorios.")

    if len(password) < 12:
        sys.exit("La contraseña debe tener al menos 12 caracteres.")

    if password != confirmation:
        sys.exit("Las contraseñas no coinciden.")

    engine = create_engine(os.environ["DATABASE_URL"])

    with Session(engine) as db:
        with db.begin():
            existing_user = db.scalar(
                select(User.id).where(User.email == email)
            )

            if existing_user is not None:
                sys.exit("Ya existe un usuario con ese correo.")

            tenant = Tenant(name=organization)
            db.add(tenant)
            db.flush()

            user = User(
                email=email,
                password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()

            membership = Membership(
                user_id=user.id,
                tenant_id=tenant.id,
                role="owner",
            )
            db.add(membership)

    engine.dispose()

    print("Administrador y organización creados correctamente.")


if __name__ == "__main__":
    main()

