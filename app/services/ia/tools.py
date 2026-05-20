"""
Definicion de tools (function calling) para el bot de WhatsApp.
"""

WHATSAPP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_estado_reparacion",
            "description": (
                "Consulta el estado detallado de una reparacion especifica por su ID. "
                "Usar cuando ya se sabe el ID de la reparacion, o cuando la conversación "
                "ya quedó verificada/seleccionada por una consulta anterior. "
                "En modo detalle también devuelve `seguimiento_publico`, que replica los "
                "datos visibles en la página de seguimiento para el cliente. "
                "Si la conversacion esta verificada, además puede retornar costos internos "
                "y datos tecnicos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id_reparacion": {
                        "type": "integer",
                        "description": (
                            "ID de la reparacion a consultar. Puede omitirse si ya quedó "
                            "verificada o seleccionada en el contexto."
                        )
                    },
                    "modo_consulta": {
                        "type": "string",
                        "enum": ["solo_fecha", "estado", "detalle"],
                        "description": (
                            "Nivel de detalle: "
                            "solo_fecha (solo fecha/hora estimada), "
                            "estado (estado general), "
                            "detalle (estado + datos adicionales)."
                        )
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_reparaciones_cliente",
            "description": (
                "Lista las reparaciones del cliente identificado por su numero de telefono. "
                "Usar cuando el cliente: menciona 'mi celular', 'mi equipo', 'lo que dejé', "
                "'mi reparacion', 'cuándo está listo', 'cómo va', o cualquier referencia a "
                "un equipo que dejó en el local para reparar. "
                "NO usar si el cliente quiere COMPRAR un equipo o producto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "telefono": {
                        "type": "string",
                        "description": "Telefono del cliente en formato internacional (ej: +595981123456)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verificar_codigo",
            "description": (
                "Verifica un codigo de 6 digitos para acceder a datos sensibles de una reparacion. "
                "El codigo fue entregado al cliente cuando dejo el equipo en el local. "
                "Usar SOLO cuando el cliente proporcione explicitamente un codigo numerico de 6 digitos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "Codigo de 6 digitos proporcionado por el cliente"
                    },
                    "telefono": {
                        "type": "string",
                        "description": "Telefono del cliente"
                    }
                },
                "required": ["codigo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_faq",
            "description": (
                "Obtiene informacion del negocio: horarios de atencion, ubicacion/direccion, "
                "garantia de reparaciones, requisitos para retirar un equipo, metodos de pago aceptados, "
                "telefonos de contacto, zonas de entrega y politica de cambios. "
                "Usar cuando el cliente pregunte por cualquiera de estos temas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tema": {
                        "type": "string",
                        "enum": ["horarios", "ubicacion", "garantia", "requisitos", "metodos_pago", "contacto", "zonas_de_entrega", "politica_cambios", "todos"],
                        "description": "Tema de la consulta"
                    }
                },
                "required": ["tema"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "estimar_precio_reparacion",
            "description": (
                "Estima un rango de precio de reparación usando historial de casos similares. "
                "Usar cuando el cliente consulta costo de reparación (ej: cambio de display, batería, pin de carga) "
                "y no hay un precio exacto cargado para ese equipo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": "Descripción libre del trabajo pedido (ej: 'cambio de display iphone 11')."
                    },
                    "tipo_equipo": {
                        "type": "string",
                        "description": "Tipo de equipo opcional (ej: celular, tablet, laptop)."
                    },
                    "marca_modelo": {
                        "type": "string",
                        "description": "Marca o modelo opcional para afinar similitud (ej: Samsung A15)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_productos",
            "description": (
                "Busca productos disponibles para la VENTA en el catalogo del local: "
                "celulares, tablets, accesorios (fundas, cargadores, auriculares), repuestos, etc. "
                "Usar cuando el cliente quiere COMPRAR algo, consultar precios de venta, "
                "o preguntar si tienen determinado producto disponible. "
                "Tambien usar para preguntas abiertas como 'cual es el celular mas barato?', 'que celulares tienen?'. "
                "NO usar para consultas sobre reparaciones de equipos del cliente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "busqueda": {
                        "type": "string",
                        "description": "Texto de busqueda: nombre, marca, modelo o tipo (ej: 'Samsung', 'iPhone', 'cargador'). Dejar vacio si la consulta es general."
                    },
                    "categoria": {
                        "type": "string",
                        "description": "Categoria opcional para filtrar (ej: 'celulares', 'accesorios', 'repuestos')"
                    },
                    "orden": {
                        "type": "string",
                        "enum": ["precio_menor", "precio_mayor", "relevancia"],
                        "description": "Criterio de orden sugerido por el cliente (ej. 'precio_menor' para el mas barato o economico)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "derivar_a_asesor",
            "description": (
                "Deriva la conversacion a un asesor humano. "
                "Usar UNICAMENTE cuando: el cliente pide EXPLICITAMENTE hablar con una persona, "
                "asesor, operador o representante humano; o cuando hay un reclamo serio o queja grave. "
                "NUNCA usar para consultas sobre productos, reparaciones, precios o informacion general. "
                "Si el mensaje es ambiguo, preguntá al cliente qué necesita ANTES de derivar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "motivo": {
                        "type": "string",
                        "description": "Motivo de la derivacion (breve descripcion)"
                    },
                    "prioridad": {
                        "type": "string",
                        "enum": ["normal", "urgente"],
                        "description": "Prioridad de la derivacion"
                    }
                },
                "required": ["motivo"]
            }
        }
    }
]
