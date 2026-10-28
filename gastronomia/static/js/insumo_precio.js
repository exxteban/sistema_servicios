(function () {
  // El precio de compra se guarda por unidad base (g, ml, unidad). Para que nadie tenga que dividir,
  // en pantalla se pide como se compra: gramos -> por kilo, mililitros -> por litro, resto -> por unidad.
  const FACTORES = {g: 1000, ml: 1000};
  const ETIQUETAS = {g: 'el kilo', ml: 'el litro', mazo: 'el mazo', porcion: 'la porcion'};

  window.GastroPrecioInsumo = {
    etiqueta: (unidad) => ETIQUETAS[unidad] || 'la unidad',
    // Precio guardado (por g/ml/unidad) -> precio que se muestra (por kilo/litro/unidad).
    aPantalla: (precio, unidad) => Math.round(Number(precio || 0) * (FACTORES[unidad] || 1)),
    // Precio escrito (por kilo/litro/unidad) -> precio a guardar por unidad base.
    aBase: (valor, unidad) => Number(valor || 0) / (FACTORES[unidad] || 1),
  };
}());
