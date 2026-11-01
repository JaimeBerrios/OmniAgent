from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Customer, Membership, Tenant, User
from .schemas import (
    CustomerResponse,
    LoginRequest,
    TokenResponse,
)
from .security import (
    create_access_token,
    get_current_user,
    require_tenant_membership,
    verify_password,
)

from fastapi import status
from sqlalchemy.exc import IntegrityError
from .schemas import CustomerCreate

app = FastAPI(
    title="OmniAgent API",
    description="API del sistema de atención omnicanal OmniAgent",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "application": "OmniAgent",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


@app.post("/auth/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    email = credentials.email.strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if (
        user is None
        or not user.is_active
        or not verify_password(
            credentials.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id)
    )


@app.get("/auth/me")
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_active": current_user.is_active,
    }


@app.get("/tenants/{tenant_id}/me")
def get_my_tenant(
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, membership.tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Organización no encontrada",
        )

    return {
        "tenant_id": tenant.id,
        "organization": tenant.name,
        "role": membership.role,
    }


@app.get(
    "/tenants/{tenant_id}/customers",
    response_model=list[CustomerResponse],
)
def list_customers(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    customers = db.scalars(
        select(Customer)
        .where(Customer.tenant_id == membership.tenant_id)
        .order_by(Customer.id)
    ).all()

    return customers


@app.post(
    "/tenants/{tenant_id}/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    tenant_id: int,
    customer_data: CustomerCreate,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para registrar clientes",
        )

    customer = Customer(
        tenant_id=membership.tenant_id,
        external_id=customer_data.external_id,
        name=customer_data.name,
    )

    try:
        db.add(customer)
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un cliente con ese identificador en la organización",
        )

    return customer
