from sqlalchemy import Column, Integer, String, Date, JSON
from database import Base, engine

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    user_info = Column(JSON)

class DailyLog(Base):
    __tablename__ = 'daily_logs'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer)
    date = Column(Date)
    data = Column(JSON)

Base.metadata.create_all(engine)
