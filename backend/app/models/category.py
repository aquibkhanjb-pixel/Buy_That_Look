"""Category model for standardized taxonomy."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Category(Base):
    """
    Category model for unified product taxonomy.

    Supports hierarchical categories (e.g., Women > Clothing > Dresses).
    Maps site-specific categories to standardized names.
    """

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    level = Column(Integer, default=0)
    path = Column(String(500), nullable=True)  # e.g., "Women > Clothing > Dresses"

    # Self-referential relationship for hierarchy
    parent = relationship("Category", remote_side=[id], backref="children")

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name={self.name})>"

    def to_dict(self) -> dict:
        """Convert category to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "level": self.level,
            "path": self.path,
        }

    @property
    def full_path(self) -> str:
        """Get full category path."""
        if self.path:
            return self.path
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name
