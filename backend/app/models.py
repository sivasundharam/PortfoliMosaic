from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    documents = relationship("Document", back_populates="owner")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, index=True, nullable=True)  # Session isolation
    document_id = Column(String, unique=True, index=True, nullable=False)
    filename = Column(String, nullable=False)
    document_type = Column(String, nullable=True)
    extraction_status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Landing AI ADE fields
    markdown = Column(Text, nullable=True)  # Parsed markdown from PDF
    extraction_json = Column(Text, nullable=True)  # Structured JSON from ADE
    categorized_data = Column(Text, nullable=True)  # Categorized extraction data
    ade_metadata = Column(Text, nullable=True)  # ADE metadata (confidence scores, etc.)

    owner = relationship("User", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document")
    holdings = relationship("Holding", back_populates="document")
    bs_items = relationship("BalanceSheetItem", back_populates="document")
    is_items = relationship("IncomeStatementItem", back_populates="document")
    cf_items = relationship("CashFlowItem", back_populates="document")


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, index=True)
    document_ref = Column(String, index=True, nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_id = Column(String, index=True, nullable=False)
    content = Column(Text, nullable=False)

    document = relationship("Document", back_populates="chunks")


class Holding(Base):
    __tablename__ = "holdings"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    symbol = Column(String, index=True, nullable=False)
    quantity = Column(Float, nullable=False)
    currency = Column(String, default="USD")

    # Brokerage account information
    brokerage_firm = Column(String, index=True, nullable=True)  # e.g., "Fidelity", "Charles Schwab"
    account_number = Column(String, nullable=True)  # Account number
    account_type = Column(String, nullable=True)  # e.g., "Individual", "IRA", "401k"

    # Security details
    security_name = Column(String, nullable=True)  # Full name of security (e.g., "Apple Inc.")

    # Price and value information
    price_per_unit = Column(Float, nullable=True)  # Price per share/unit at statement date
    market_value = Column(Float, nullable=True)  # Total market value (quantity * price)
    cost_basis = Column(Float, nullable=True)  # Original purchase cost

    # Gain/Loss information
    gain_loss = Column(Float, nullable=True)  # Unrealized gain/loss amount
    gain_loss_percent = Column(Float, nullable=True)  # Gain/loss percentage

    document = relationship("Document", back_populates="holdings")


class BalanceSheetItem(Base):
    __tablename__ = "balance_sheet_items"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    value = Column(Float, nullable=False)
    period = Column(String, default="latest")

    document = relationship("Document", back_populates="bs_items")


class IncomeStatementItem(Base):
    __tablename__ = "income_statement_items"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    value = Column(Float, nullable=False)
    period = Column(String, default="latest")

    document = relationship("Document", back_populates="is_items")


class CashFlowItem(Base):
    __tablename__ = "cash_flow_items"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    value = Column(Float, nullable=False)
    period = Column(String, default="latest")

    document = relationship("Document", back_populates="cf_items")
