"""Celery worker ishga tushganda Django sozlamalari yuklanishi uchun."""
from .celery import app as celery_app

__all__ = ("celery_app",)
