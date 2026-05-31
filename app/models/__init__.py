"""
Modelos SQLAlchemy - Sistema de Inventario y Ventas
"""
from app.models.usuario import Usuario, PreferenciaUsuario
from app.models.rol import Rol
from app.models.permiso import Permiso
from app.models.autorizacion import Autorizacion
from app.models.auditoria import Auditoria
from app.models.producto import Producto, Categoria, ProductoCompuesto, ProductoRepuesto, ProductoPrecioOpcion
from app.models.producto_presentacion import ProductoPresentacionStock
from app.models.servicio import Servicio, ServicioPrecioOpcion, ClienteServicio
from app.models.cliente import Cliente, ClienteObservacion
from app.models.cliente_calificacion import ClienteCalificacionRegla, ClienteCalificacionHistorial
from app.models.cliente_fidelizacion import ClienteFidelizacionMovimiento
from app.models.proveedor import Proveedor
from app.models.caja import Caja, SesionCaja, MovimientoCaja, ColaCobro
from app.models.venta import Venta, DetalleVenta, PagoVenta, MetodoPago, CuentaPorCobrar, PagoCuentaCobrar, Ticket
from app.models.compra import Compra, DetalleCompra, PagoCompra, CuentaPorPagar
from app.models.devolucion import Devolucion, DetalleDevolucion
from app.models.inventario import MovimientoStock, AjusteInventario, DetalleAjusteInventario
from app.models.configuracion import Configuracion
from app.models.reparacion import Reparacion, DetalleReparacion
from app.models.recepcion_usado import VendedorUsado, RecepcionCompraUsado
from app.models.presupuesto_empresarial import PresupuestoEmpresarial
from app.models.whatsapp import (
    WhatsAppConversacion, WhatsAppMensaje, WhatsAppConfiguracion,
    WhatsAppEstadoAsesor, WhatsAppAsignacionConversacion, WhatsAppCodigoVerificacion,
    WhatsAppConversacionEvento
)
from app.models.crm_etiqueta import CrmEtiqueta
from app.models.crm_contacto import CrmContacto
from app.models.crm_nota_interna import CrmNotaInterna
from app.models.crm_plantilla import CrmPlantilla
from app.models.agenda_actividad import AgendaActividad
from app.models.tienda import TiendaConfig, ProductoImagen, TiendaLead, TiendaVisitaEvento
from app.models.tienda_promocion import (
    TiendaPromocion,
    TiendaPromocionGastronomiaProducto,
    TiendaPromocionProducto,
)
from app.models.web_bot import WebBotSesion, WebBotMensaje, WebBotHandoff
from app.models.asistente_ia import AsistenteIABackofficeAudit
from app.models.publicidad_ads import PublicidadAdsEvento
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaGrupoOpciones,
    GastronomiaMesa,
    GastronomiaOpcionProducto,
    GastronomiaPedido,
    GastronomiaPedidoEvento,
    GastronomiaPedidoItem,
    GastronomiaPedidoItemModificador,
    GastronomiaPedidoPago,
    GastronomiaProducto,
)
from gastronomia.channel_models import GastronomiaProductoPrecioCanal
from gastronomia.stock_models import (
    GastronomiaOpcionInsumo,
    GastronomiaPedidoItemConsumo,
    GastronomiaRecetaInsumo,
)
from pedidos.models import PedidoCliente, PedidoClienteDetalle, PedidoClienteHistorial, PedidoClientePago
from cobranzas.models import PlanCreditoVenta, CuotaCreditoVenta, PagoCuentaCobrarAplicacion
from flujo_caja.models import FlujoCajaMovimiento, FlujoCajaPlantilla, FlujoCajaSemana
from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente

__all__ = [
    'Usuario', 'PreferenciaUsuario', 'Rol', 'Permiso', 'Autorizacion', 'Auditoria',
    'Producto', 'Categoria', 'ProductoCompuesto', 'ProductoRepuesto',
    'ProductoPrecioOpcion', 'ProductoPresentacionStock', 'Servicio', 'ServicioPrecioOpcion', 'ClienteServicio',
    'Cliente', 'ClienteObservacion', 'ClienteCalificacionRegla', 'ClienteCalificacionHistorial',
    'ClienteFidelizacionMovimiento',
    'Proveedor',
    'Caja', 'SesionCaja', 'MovimientoCaja', 'ColaCobro',
    'Venta', 'DetalleVenta', 'PagoVenta', 'MetodoPago', 'CuentaPorCobrar', 'PagoCuentaCobrar', 'Ticket',
    'Compra', 'DetalleCompra', 'PagoCompra', 'CuentaPorPagar',
    'Devolucion', 'DetalleDevolucion',
    'MovimientoStock', 'AjusteInventario', 'DetalleAjusteInventario',
    'Configuracion',
    'Reparacion', 'DetalleReparacion',
    'VendedorUsado', 'RecepcionCompraUsado',
    'PresupuestoEmpresarial',
    'WhatsAppConversacion', 'WhatsAppMensaje', 'WhatsAppConfiguracion',
    'WhatsAppEstadoAsesor', 'WhatsAppAsignacionConversacion', 'WhatsAppCodigoVerificacion',
    'WhatsAppConversacionEvento',
    'CrmEtiqueta', 'CrmContacto', 'CrmNotaInterna', 'CrmPlantilla',
    'AgendaActividad',
    'TiendaConfig', 'ProductoImagen', 'TiendaLead', 'TiendaVisitaEvento',
    'TiendaPromocion', 'TiendaPromocionProducto', 'TiendaPromocionGastronomiaProducto',
    'WebBotSesion', 'WebBotMensaje', 'WebBotHandoff',
    'AsistenteIABackofficeAudit',
    'PublicidadAdsEvento',
    'GastronomiaClienteConfig', 'GastronomiaCategoria', 'GastronomiaProducto', 'GastronomiaProductoPrecioCanal',
    'GastronomiaGrupoOpciones', 'GastronomiaOpcionProducto', 'GastronomiaMesa',
    'GastronomiaPedido', 'GastronomiaPedidoItem', 'GastronomiaPedidoItemModificador',
    'GastronomiaPedidoEvento', 'GastronomiaPedidoPago',
    'GastronomiaRecetaInsumo', 'GastronomiaOpcionInsumo', 'GastronomiaPedidoItemConsumo',
    'PedidoCliente', 'PedidoClienteDetalle', 'PedidoClienteHistorial', 'PedidoClientePago',
    'PlanCreditoVenta', 'CuotaCreditoVenta', 'PagoCuentaCobrarAplicacion',
    'FlujoCajaSemana', 'FlujoCajaMovimiento', 'FlujoCajaPlantilla',
    'GastoCorriente', 'PagoGastoCorriente',
]
