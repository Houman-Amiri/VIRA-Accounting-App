"""Persistent catalog lifecycle, under Database's BEGIN IMMEDIATE transaction.

A used choice is deactivated, never detached from history. Immutable identities
and canonical production semantics prevent silent reclassification/conversion.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import InventoryItem, ItemType, ItemUnit, Supplier
from ..schemas.catalog import CatalogCategory, CatalogDeletion, clean_name
from .errors import DomainError, DuplicateEntityError, NotFoundError, StaleVersionError
from .security_audit import record_security_event


class CatalogService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def model(category: CatalogCategory) -> type[ItemType] | type[ItemUnit]:
        return ItemType if category == "types" else ItemUnit

    def list(self, category: CatalogCategory, *, active_only: bool = False) -> list[Any]:
        model = self.model(category)
        query = select(model).order_by(model.name)
        if active_only:
            query = query.where(model.is_active == 1)
        return list(self.session.scalars(query))

    def get(self, category: CatalogCategory, ident: str) -> Any:
        row = self.session.get(self.model(category), ident)
        if row is None:
            raise NotFoundError("گزینهٔ اطلاعات پایه پیدا نشد")
        return row

    @staticmethod
    def check_version(row: Any, version_id: int) -> None:
        if row.version_id != version_id:
            raise StaleVersionError("این گزینه هم‌زمان تغییر کرده است؛ فهرست را تازه کنید")

    def ensure_name(self, model: Any, name: str, *, exclude: str | None = None) -> None:
        for row in self.session.scalars(select(model)):
            if row.id == exclude:
                continue
            # Preserve legacy supplier spelling; do not rewrite/merge old rows.
            try:
                same = clean_name(row.name).casefold() == clean_name(name).casefold()
            except ValueError:
                same = row.name == name
            if same:
                raise DuplicateEntityError(
                    "این نام قبلاً ثبت شده است؛ گزینهٔ غیرفعال را دوباره فعال کنید"
                )

    def event(self, category: str, row: Any, action: str, actor_id: str | None) -> None:
        record_security_event(
            self.session,
            "CATALOG_CHANGED",
            actor_id=actor_id,
            detail={
                "category": category,
                "id": row.id,
                "name": row.name,
                "action": action,
                "is_active": bool(row.is_active),
                "version_id": row.version_id,
            },
        )

    def create(self, category: CatalogCategory, name: str, actor_id: str | None) -> Any:
        model = self.model(category)
        self.ensure_name(model, name)
        now = utc_now_iso()
        row = model(
            id=uuid7(), name=name, is_active=1, version_id=1, created_at=now, updated_at=now
        )
        self.session.add(row)
        self.session.flush()
        self.event(category, row, "created", actor_id)
        return row

    def activate(
        self,
        category: CatalogCategory,
        ident: str,
        version: int,
        active: bool,
        actor_id: str | None,
    ) -> Any:
        row = self.get(category, ident)
        self.check_version(row, version)
        row.is_active = int(active)
        row.version_id += 1
        row.updated_at = utc_now_iso()
        self.session.flush()
        self.event(category, row, "reactivated" if active else "deactivated", actor_id)
        return row

    def delete(
        self, category: str, ident: str, version: int, actor_id: str | None
    ) -> CatalogDeletion:
        if category == "suppliers":
            row = self.session.get(Supplier, ident)
            column = InventoryItem.supplier_id
            pinned = False
        else:
            row = self.get("types" if category == "types" else "units", ident)
            column = InventoryItem.kind if category == "types" else InventoryItem.unit
            pinned = ident in {"FILAMENT", "PRODUCT", "G", "PCS"}
        if row is None:
            raise NotFoundError("گزینه پیدا نشد")
        self.check_version(row, version)
        used = bool(
            self.session.scalar(
                select(func.count()).select_from(InventoryItem).where(column == ident)
            )
        )
        if category == "units":
            used = used or bool(self.session.scalar(select(func.count()).select_from(ItemType).where(ItemType.required_unit == ident)))
        if used or pinned:
            row.is_active = 0
            row.version_id += 1
            row.updated_at = utc_now_iso()
            self.session.flush()
            self.event(category, row, "deactivated", actor_id)
            return CatalogDeletion(
                action="deactivated",
                version_id=row.version_id,
                reason="برای حفظ ارجاع و سوابق، گزینه غیرفعال شد و حذف فیزیکی نشد؛ فعال‌سازی مجدد ممکن است.",
            )
        self.event(category, row, "deleted", actor_id)
        self.session.delete(row)
        self.session.flush()
        return CatalogDeletion(action="deleted", reason="گزینهٔ استفاده‌نشده حذف شد.")

    def validate_item(self, kind: str, unit: str, supplier_id: str | None) -> None:
        item_type = self.get("types", kind)
        item_unit = self.get("units", unit)
        if not item_type.is_active or not item_unit.is_active:
            raise DomainError("نوع یا واحد غیرفعال برای ثبت کالای جدید مجاز نیست")
        if item_type.required_unit and item_type.required_unit != unit:
            raise DomainError(
                "واحد فیلامنت باید گرم و واحد محصول تولیدی باید عدد باشد؛ تبدیل واحد خودکار انجام نمی‌شود"
            )
        if supplier_id:
            supplier = self.session.get(Supplier, supplier_id)
            if supplier is None:
                raise NotFoundError("تأمین‌کننده پیدا نشد")
            if not supplier.is_active:
                raise DomainError("انتخاب تأمین‌کنندهٔ غیرفعال مجاز نیست")
