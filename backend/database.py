"""Database configuration and utilities"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

# Load environment variables from .env
load_dotenv()

# Get database configuration from environment
MONGO_URL = os.getenv('MONGO_URL')
DB_NAME = os.getenv('DB_NAME', 'trading_db')

if not MONGO_URL:
    raise ValueError(
        "MONGO_URL environment variable is not set. "
        "Please add MONGO_URL to your .env file:\n"
        "Example: MONGO_URL=mongodb://localhost:27017/trading_db"
    )

if not DB_NAME:
    raise ValueError("DB_NAME environment variable is not set")

# Initialize MongoDB client
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

logger.info(f"Connected to MongoDB database: {DB_NAME}")


async def get_db():
    """Get database instance"""
    return db


async def close_db():
    """Close database connection"""
    if client:
        client.close()
        logger.info("Closed MongoDB connection")
