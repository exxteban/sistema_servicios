// Productos por kilo (tortas enteras): el precio es por kg y no se piden desde la web,
// porque el pedido web no carga peso. El servidor tambien los rechaza.
export const TEXTO_POR_PESO = 'Se vende por peso: consultalo con el local.'

export const esPorPeso = (producto) => producto?.unidad_venta === 'kg'
