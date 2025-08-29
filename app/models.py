# app/models.py
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB  # Postgres JSONB

# ---- Postgres only ----
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    user = os.getenv("POSTGRES_USER", "buildportal")
    password = os.getenv("POSTGRES_PASSWORD", "buildportal")
    db = os.getenv("POSTGRES_DB", "buildportal")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    DATABASE_URL = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("DATABASE_URL pointe vers SQLite, on veut Postgres.")

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class TestRun(Base):
    __tablename__ = "test_runs"
    id = Column(Integer, primary_key=True)
    suite_name = Column(String)
    result = Column(String)
    duration = Column(String)
    total_tests = Column(Integer)
    passed_tests = Column(Integer)
    failed_tests = Column(Integer)
    inconclusive_tests = Column(Integer)
    skipped_tests = Column(Integer)
    failure_message = Column(Text)
    report_id = Column(String)
    branch = Column(String)
    project = Column(String)
    extra_data = Column(JSONB)
    jenkins_url = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    test_results = relationship("TestResult", back_populates="test_run")

class TestResult(Base):
    __tablename__ = "test_results"
    id = Column(Integer, primary_key=True)
    test_name = Column(String)
    status = Column(String)
    changeset_id = Column(String)
    label = Column(String)
    unity_version = Column(String)
    developer_email = Column(String)
    duration = Column(String)
    message = Column(Text)
    stack_trace = Column(Text)
    output = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    test_run_id = Column(Integer, ForeignKey('test_runs.id'))
    test_run = relationship("TestRun", back_populates="test_results")

def init_db():
    Base.metadata.create_all(bind=engine)

def save_result(obj):
    session = SessionLocal()
    try:
        session.add(obj)
        session.commit()
    finally:
        session.close()
