from sqlalchemy import Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key= True, autoincrement= True)
    email = Column(String(320), unique= True, nullable= False, index= True)
    hashed_password = Column(String, nullable= False)
    full_name = Column(String, nullable= True)


class Transactions(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key= True, autoincrement= True)
    date = Column(String, nullable= True)
    description = Column(Text, nullable= True)
    merchant = Column(String, nullable= True)
    amount = Column(Float, nullable = False, default= 0.0)
    category = Column(String, nullable = True)
    user_id = Column(Integer, nullable= True, index = True) #   Will Link to users.id later