# Seguridad Y Control Root

## Regla Principal

La IA del asistente interno solo puede ser habilitada o deshabilitada por el usuario root del sistema.

El usuario root es el dueño operativo del SaaS. Aunque existan administradores de clientes o supervisores, no deben poder activar ni apagar esta función global.

## Configuración Global

Crear configuraciones separadas de la IA actual del bot:

```text
ia_backoffice_enabled
ia_backoffice_provider
ia_backoffice_model
ia_backoffice_deepseek_base_url
ia_backoffice_max_tokens
ia_backoffice_temperature
ia_backoffice_daily_token_budget
ia_backoffice_monthly_token_budget
ia_backoffice_readonly_mode
ia_backoffice_advanced_model_enabled
```

La configuración actual `ia_enabled` puede seguir existiendo para WhatsApp/bot. No mezclar ambos interruptores.

Defaults recomendados:

```text
ia_backoffice_provider=deepseek
ia_backoffice_model=deepseek-v4-flash
ia_backoffice_deepseek_base_url=https://api.deepseek.com
ia_backoffice_advanced_model_enabled=false
```

`deepseek-v4-pro` solo debe activarse para consultas avanzadas si root lo permite.

## Root Only

Crear una función centralizada:

```python
def es_usuario_root(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (
            getattr(user, "username", "") == "root"
            or int(getattr(user, "id_rol", 0) or 0) == 1
        )
    )
```

Recomendación: si en producción hay varios usuarios con rol administrador, conviene agregar una preferencia o configuración explícita:

```text
system_root_user_id
```

Así solo tu usuario exacto puede tocar el switch global.

## Permisos De Uso

Separar dos permisos:

```text
usar_asistente_ia
gestionar_asistente_ia
```

Reglas:

- Root puede habilitar/deshabilitar globalmente.
- Root puede decidir qué roles usan el asistente.
- Un usuario puede usar el asistente solo si:
  - IA global está habilitada.
  - Tiene permiso `usar_asistente_ia`.
  - Tiene permisos del módulo consultado.

Ejemplo: si pregunta por cobranzas, también debe tener permiso de ver cobranzas o reportes equivalentes.

## Scope De Datos

El modelo nunca recibe ni decide `cliente_id`.

Cada handler debe resolver el alcance desde backend:

```python
cliente_scope = getattr(current_user, "id_cliente", None)
```

Para módulos multi-tenant:

- Gastos corrientes: filtrar por `cliente_id`.
- Control de empleados: filtrar por `cliente_id`.
- Tienda online: filtrar por `id_cliente` de tienda.
- Productos de tienda: usar reglas existentes de scope.

Atención: en ventas y cobranzas, `id_cliente` representa cliente comprador. Antes de aplicar multi-tenant allí, confirmar el modelo de datos real de tenant para no filtrar mal.

## Auditoría

Registrar por cada interacción:

```text
id_usuario
username
fecha_hora
pregunta
respuesta
tools_usadas
argumentos_normalizados
resultado_resumido
tokens_prompt
tokens_completion
tokens_total
modelo
provider
estado
ip
user_agent
```

No guardar API keys ni datos sensibles completos.

## Rate Limits

Controles mínimos:

- Máximo mensajes por usuario por minuto.
- Máximo mensajes por usuario por día.
- Presupuesto diario global de tokens.
- Presupuesto mensual global de tokens.
- Límite separado para uso de modelo avanzado.
- Corte automático si la tool devuelve demasiados datos.

## Modo Seguro

El MVP debe funcionar en modo solo lectura:

```text
ia_backoffice_readonly_mode=true
```

En este modo la IA puede consultar y explicar, pero no modificar datos.

## Reglas Anti Riesgo

- No permitir SQL generado por la IA.
- No permitir nombres de tabla libres como argumentos.
- No permitir filtros arbitrarios no validados.
- No permitir que el usuario fuerce `cliente_id`.
- No permitir que el modelo vea claves, tokens, contraseñas o hashes.
- No permitir acciones destructivas sin una fase futura de confirmación explícita.
