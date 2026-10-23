from sqlalchemy import String, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, default='CT-200 Manual')
    versions: Mapped[list['DocumentVersion']] = relationship(back_populates='document', cascade='all, delete-orphan')
class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id'))
    version_number: Mapped[int] = mapped_column(Integer)
    source_filename: Mapped[str] = mapped_column(String(500))
    source_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    document: Mapped[Document] = relationship(back_populates='versions')
    nodes: Mapped[list['Node']] = relationship(back_populates='version', cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('document_id','version_number'),)
class Node(Base):
    __tablename__ = 'nodes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logical_id: Mapped[str] = mapped_column(String(36), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey('document_versions.id'), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('nodes.id'), nullable=True)
    heading: Mapped[str] = mapped_column(Text)
    number: Mapped[str] = mapped_column(String(80), default='')
    level: Mapped[int] = mapped_column(Integer)
    body_text: Mapped[str] = mapped_column(Text, default='')
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_start: Mapped[int] = mapped_column(Integer, default=1)
    page_end: Mapped[int] = mapped_column(Integer, default=1)
    node_type: Mapped[str] = mapped_column(String(30), default='section')
    version: Mapped[DocumentVersion] = relationship(back_populates='nodes')
    parent: Mapped['Node | None'] = relationship(remote_side=[id], back_populates='children')
    children: Mapped[list['Node']] = relationship(back_populates='parent', cascade='all, delete-orphan', order_by='Node.id')
class Selection(Base):
    __tablename__ = 'selections'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(40))
    items: Mapped[list['SelectionItem']] = relationship(back_populates='selection', cascade='all, delete-orphan')
class SelectionItem(Base):
    __tablename__ = 'selection_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey('selections.id'))
    node_id: Mapped[int] = mapped_column(ForeignKey('nodes.id'))
    version_id: Mapped[int] = mapped_column(ForeignKey('document_versions.id'))
    logical_id: Mapped[str] = mapped_column(String(36))
    content_hash: Mapped[str] = mapped_column(String(64))
    snapshot_heading: Mapped[str] = mapped_column(Text)
    snapshot_text: Mapped[str] = mapped_column(Text)
    selection: Mapped[Selection] = relationship(back_populates='items')
