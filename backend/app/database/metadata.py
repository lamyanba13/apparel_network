from sqlalchemy import MetaData

from app.database.naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)
