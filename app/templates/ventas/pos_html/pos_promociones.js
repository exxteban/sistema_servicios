            subtotalItemPromocion(item) {
                const precio = parseFloat(item?.precio) || 0;
                const cantidad = parseInt(item?.cantidad) || 0;
                const subtotalGuardado = parseFloat(item?.subtotal_guardado);
                if (Number.isFinite(subtotalGuardado) && parseInt(item?.subtotal_guardado_cantidad) === cantidad) {
                    return subtotalGuardado;
                }
                const promo = item?.promocion_activa;
                if (!promo || promo.tipo !== 'cantidad' || item.precio_manual || item.precio_opcion_id || this.usaPrecioMayorista()) {
                    return precio * cantidad;
                }
                const lleva = parseInt(promo.cantidad_lleva) || 0;
                const paga = parseInt(promo.cantidad_paga) || 0;
                const bonificadas = lleva > paga ? Math.floor(cantidad / lleva) * (lleva - paga) : 0;
                return precio * (cantidad - bonificadas);
            },
