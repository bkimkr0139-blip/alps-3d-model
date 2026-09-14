from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Product, Variant
from app.schemas.product import ProductCreate, ProductRead, VariantCreate, VariantRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["products"])

CAN_MANAGE_PRODUCT = require_role("program_manager", "system_architect")


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PRODUCT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    def compute() -> tuple[int, dict]:
        product = Product(
            business_id=body.business_id,
            name=body.name,
            description=body.description,
            created_by=user.username,
        )
        db.add(product)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="product",
            entity_id=product.id,
            correlation_id=correlation_id,
            payload={"business_id": product.business_id, "name": product.name},
        )
        return status.HTTP_201_CREATED, ProductRead.model_validate(product).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/products", response_model=list[ProductRead])
def list_products(db: Annotated[Session, Depends(get_db)]):
    return db.query(Product).order_by(Product.created_at).all()


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: str, db: Annotated[Session, Depends(get_db)]):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    return product


@router.get("/products/{product_id}/variants", response_model=list[VariantRead])
def list_variants(product_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(Variant).filter_by(product_id=product_id).order_by(Variant.created_at).all()


@router.post(
    "/products/{product_id}/variants",
    response_model=VariantRead,
    status_code=status.HTTP_201_CREATED,
)
def create_variant(
    product_id: str,
    body: VariantCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PRODUCT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")

    def compute() -> tuple[int, dict]:
        variant = Variant(
            business_id=body.business_id,
            product_id=product.id,
            name=body.name,
            description=body.description,
            created_by=user.username,
        )
        db.add(variant)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="variant",
            entity_id=variant.id,
            correlation_id=correlation_id,
            payload={"business_id": variant.business_id, "product_id": str(product.id)},
        )
        return status.HTTP_201_CREATED, VariantRead.model_validate(variant).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/variants/{variant_id}", response_model=VariantRead)
def get_variant(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    variant = db.get(Variant, variant_id)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    return variant
