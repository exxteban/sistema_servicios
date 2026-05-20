from datetime import datetime

from app import db


class PublicidadAdsEvento(db.Model):
    __tablename__ = 'publicidad_ads_eventos'

    id_evento = db.Column(db.Integer, primary_key=True)
    landing_key = db.Column(db.String(40), nullable=False, default='publicidad_ads', index=True)
    tipo_evento = db.Column(db.String(40), nullable=False, index=True)
    etiqueta = db.Column(db.String(120), nullable=True, index=True)
    section_id = db.Column(db.String(80), nullable=True, index=True)
    path_url = db.Column(db.String(255), nullable=True)
    session_hash = db.Column(db.String(80), nullable=True, index=True)
    visitante_hash = db.Column(db.String(64), nullable=False, index=True)
    utm_source = db.Column(db.String(120), nullable=True, index=True)
    utm_medium = db.Column(db.String(120), nullable=True, index=True)
    utm_campaign = db.Column(db.String(120), nullable=True, index=True)
    utm_term = db.Column(db.String(120), nullable=True)
    utm_content = db.Column(db.String(120), nullable=True)
    referer_url = db.Column(db.String(500), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    payload_json = db.Column(db.Text, nullable=True)
    fecha_evento = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        db.Index('ix_publicidad_ads_eventos_tipo_fecha', 'tipo_evento', 'fecha_evento'),
        db.Index('ix_publicidad_ads_eventos_landing_fecha', 'landing_key', 'fecha_evento'),
    )

    def __repr__(self):
        return f'<PublicidadAdsEvento id={self.id_evento} tipo={self.tipo_evento} landing={self.landing_key}>'
