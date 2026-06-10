import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = os.getenv('SECRET_KEY', 'dev')
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI')
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'media', 'images')
