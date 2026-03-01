from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    projects: Mapped[list["Project"]] = relationship(back_populates="user")


class Project(Base):
    __tablename__ = "projects_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="projects")
    mpzp_conditions: Mapped["MPZPConditions"] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    cost_estimate: Mapped["CostEstimate"] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    design_assets: Mapped[list["DesignAsset"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class MPZPConditions(Base):
    __tablename__ = "mpzp_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects_v2.id", ondelete="CASCADE"), unique=True, index=True)
    plot_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cadastral_district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    land_use_primary: Mapped[str | None] = mapped_column(Text, nullable=True)
    land_use_allowed: Mapped[str | None] = mapped_column(Text, nullable=True)
    land_use_forbidden: Mapped[str | None] = mapped_column(Text, nullable=True)
    services_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    nuisance_services_forbidden: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    parcel_area_total: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_building_height: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_storeys_above: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_storeys_below: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_ridge_height: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_eaves_height: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_building_intensity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_building_intensity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_building_coverage: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_biologically_active_share: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    min_front_elevation_width: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_front_elevation_width: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    roof_type_allowed: Mapped[str | None] = mapped_column(Text, nullable=True)
    roof_slope_min_deg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    roof_slope_max_deg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ridge_direction_required: Mapped[str | None] = mapped_column(Text, nullable=True)
    roof_cover_material_limits: Mapped[str | None] = mapped_column(Text, nullable=True)
    facade_roof_color_limits: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_height: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_area: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    building_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    roof_angle: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    biologically_active_area: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    allowed_functions: Mapped[str | None] = mapped_column(Text, nullable=True)
    parking_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intensity_min: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    intensity_max: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    frontage_min: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    floors_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basement_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped[Project] = relationship(back_populates="mpzp_conditions")
    land_use_register_items: Mapped[list["MPZPLandUseRegisterItem"]] = relationship(
        back_populates="mpzp_conditions", cascade="all, delete-orphan"
    )


class MPZPLandUseRegisterItem(Base):
    __tablename__ = "mpzp_land_use_register_items"
    __table_args__ = (
        CheckConstraint("area >= 0", name="ck_mpzp_land_use_register_item_area_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("mpzp_conditions.id", ondelete="CASCADE"), index=True)
    category_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    area: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    mpzp_conditions: Mapped[MPZPConditions] = relationship(back_populates="land_use_register_items")


class CostEstimate(Base):
    __tablename__ = "cost_estimates_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects_v2.id", ondelete="CASCADE"), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    net_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    gross_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    contingency_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped[Project] = relationship(back_populates="cost_estimate")
    items: Mapped[list["CostItem"]] = relationship(back_populates="estimate", cascade="all, delete-orphan")


class CostItem(Base):
    __tablename__ = "cost_items"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_cost_item_quantity_non_negative"),
        CheckConstraint("unit_price >= 0", name="ck_cost_item_unit_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("cost_estimates_v2.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    estimate: Mapped[CostEstimate] = relationship(back_populates="items")


class DesignAsset(Base):
    __tablename__ = "design_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "dimension", "version", name="uq_asset_project_dim_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects_v2.id", ondelete="CASCADE"), index=True)
    dimension: Mapped[str] = mapped_column(Enum("2D", "3D", name="asset_dimension"))
    kind: Mapped[str] = mapped_column(String(80))
    file_path: Mapped[str] = mapped_column(String(512))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(Enum("draft", "ready", "archived", name="asset_status"), default="draft")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped[Project] = relationship(back_populates="design_assets")
