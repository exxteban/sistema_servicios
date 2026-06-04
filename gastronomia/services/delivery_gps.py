"""Reglas compartidas para publicar ubicaciones GPS de delivery."""

from __future__ import annotations

from app import db
from gastronomia.models import GastronomiaDeliveryUbicacion


GPS_PRECISION_MAXIMA_PUBLICABLE_M = 500


def ubicacion_delivery_publicable_filter():
    return db.or_(
        GastronomiaDeliveryUbicacion.precision_metros.is_(None),
        GastronomiaDeliveryUbicacion.precision_metros <= GPS_PRECISION_MAXIMA_PUBLICABLE_M,
    )
