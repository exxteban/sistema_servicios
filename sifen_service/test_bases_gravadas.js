'use strict';

/**
 * Prueba de `corregirTotalesIVA`. Se corre a mano:
 *
 *     node test_bases_gravadas.js
 *
 * No firma ni transmite: sólo genera el XML con xmlgen y comprueba los dos
 * invariantes que SIFEN valida, y que nos costaron los rechazos `2377` y
 * `2371` del 2026-09-22:
 *
 *   1. cada agregado declarado queda a menos de medio guaraní del valor real
 *      que SIFEN recalcula desde los ítems;
 *   2. cada total es exactamente la suma de sus dos partes.
 *
 * El segundo importa tanto como el primero: los dos rechazos fueron totales
 * que se habían despegado de sus partes por redondeos independientes.
 *
 * La suite de Python no puede cubrir esto: el defecto está en el borde con la
 * librería, del lado de Node, y sólo se ve en el XML ya generado.
 */
const xmlgenLib = require('facturacionelectronicapy-xmlgen');
const xmlgen = xmlgenLib.default || xmlgenLib;
const { corregirTotalesIVA } = require('./index.js');

const TOLERANCIA = 0.5;

const params = {
  version: 150,
  ruc: '80000000-0',
  razonSocial: 'EMISOR DE PRUEBA',
  actividadesEconomicas: [{ codigo: '47723', descripcion: 'Comercio al por menor' }],
  timbradoNumero: '80000000',
  timbradoFecha: '2026-09-15',
  tipoContribuyente: 2,
  establecimientos: [{
    codigo: '001', direccion: 'Calle de prueba', numeroCasa: '0',
    departamento: 12, distrito: 153, ciudad: 3568,
    telefono: '0971000000', email: 'prueba@example.com', denominacion: 'Casa Matriz',
  }],
};

const item = (codigo, precio, iva) => ({
  codigo, descripcion: 'Item ' + codigo, unidadMedida: 77, cantidad: 1,
  precioUnitario: precio, cambio: 0, descuento: 0, anticipo: 0,
  pais: 'PRY', ivaTipo: 1, iva, ivaProporcion: 100,
});

// Los tres primeros son los DE reales de la tanda del 2026-09-22.
const casos = [
  { nombre: 'tasa unica 10% (DE 0000012, aprobado)', items: [item('A', 344343, 10), item('B', 550000, 10)] },
  { nombre: 'mezcla 5/10 (DE 0000015, aprobado)', items: [item('A', 301000, 5), item('B', 348000, 10), item('C', 194000, 10)] },
  { nombre: 'mezcla 5/10 (DE 0000016, rechazado 2377)', items: [item('A', 301000, 5), item('C', 194000, 10)] },
  { nombre: 'tasa unica 5%', items: [item('A', 301000, 5), item('B', 77777, 5)] },
  {
    nombre: 'mezcla 5/10 con descuento (DE 0000017, rechazado 2371)',
    items: [
      Object.assign(item('A', 344343, 10), { descuento: 17217 }),
      Object.assign(item('B', 301000, 5), { descuento: 15050 }),
    ],
  },
  // El exento va con ivaTipo 3 e ivaProporcion 0, igual que lo arma
  // `data_builder._item_iva`; no aporta base gravada y no debe descuadrar el total.
  {
    nombre: 'mezcla 5/10 con una linea exenta',
    items: [
      item('A', 301000, 5),
      item('B', 194000, 10),
      Object.assign(item('C', 50000, 0), { ivaTipo: 3, ivaProporcion: 0 }),
    ],
  },
];

const leer = (xml, tag) => {
  const m = xml.match(new RegExp('<' + tag + '>([^<]*)</' + tag + '>'));
  return m ? parseFloat(m[1]) : null;
};

(async () => {
  let fallas = 0;
  for (const caso of casos) {
    const total = caso.items.reduce((a, i) => a + (i.precioUnitario - (i.descuento || 0)) * i.cantidad, 0);
    const data = {
      tipoDocumento: 1, establecimiento: '001', punto: '001', numero: '0000001',
      codigoSeguridadAleatorio: '123456789', fecha: '2026-09-22T11:43:30',
      tipoEmision: 1, tipoTransaccion: 1, tipoImpuesto: 1, moneda: 'PYG',
      factura: { presencia: 1 },
      cliente: {
        razonSocial: 'Cliente de prueba', pais: 'PRY', contribuyente: false,
        tipoOperacion: 2, documentoTipo: 1, documentoNumero: '1234567',
      },
      condicion: { tipo: 1, entregas: [{ tipo: 1, monto: String(total), moneda: 'PYG', cambio: 0 }] },
      items: caso.items,
    };

    const crudo = await xmlgen.generateXMLDE(params, data);
    const corregido = corregirTotalesIVA(crudo);

    // Lo que SIFEN recalcula: los valores de cada ítem, con sus 8 decimales.
    const porTasa = { 5: { base: 0, iva: 0 }, 10: { base: 0, iva: 0 } };
    for (const b of crudo.match(/<gCamIVA>[\s\S]*?<\/gCamIVA>/g) || []) {
      const g = (t) => (b.match(new RegExp('<' + t + '>([^<]*)</' + t + '>')) || [])[1];
      const tasa = g('dTasaIVA');
      if (!porTasa[tasa]) continue;
      porTasa[tasa].base += parseFloat(g('dBasGravIVA')) || 0;
      porTasa[tasa].iva += parseFloat(g('dLiqIVAItem')) || 0;
    }

    const esperado = {
      dBaseGrav5: porTasa[5].base,
      dBaseGrav10: porTasa[10].base,
      dTBasGraIVA: porTasa[5].base + porTasa[10].base,
      dIVA5: porTasa[5].iva,
      dIVA10: porTasa[10].iva,
      dTotIVA: porTasa[5].iva + porTasa[10].iva,
    };

    const problemas = [];
    for (const [tag, real] of Object.entries(esperado)) {
      const declarado = leer(corregido, tag);
      if (declarado === null) continue; // el campo no aplica a este documento
      const desvio = Math.abs(declarado - real);
      if (desvio >= TOLERANCIA) problemas.push(tag + ': desvio ' + desvio.toFixed(4));
    }

    // Y que las partes cierren contra su total, no sólo que cada una esté cerca.
    const cierra = (total, a, b) => {
      const t = leer(corregido, total);
      if (t === null) return true;
      return Math.abs(t - ((leer(corregido, a) || 0) + (leer(corregido, b) || 0))) < 0.005;
    };
    if (!cierra('dTBasGraIVA', 'dBaseGrav5', 'dBaseGrav10')) problemas.push('dTBasGraIVA no es la suma de sus partes');
    if (!cierra('dTotIVA', 'dIVA5', 'dIVA10')) problemas.push('dTotIVA no es la suma de sus partes');

    if (problemas.length) fallas += 1;
    console.log((problemas.length ? '  FALLA' : '  OK   ') + '  ' + caso.nombre +
      (problemas.length ? '\n         ' + problemas.join('\n         ') : ''));
  }

  if (fallas) {
    console.error('\n' + fallas + ' caso(s) fuera de la tolerancia de ' + TOLERANCIA + ' Gs.');
    process.exit(1);
  }
  console.log('\n' + casos.length + ' casos dentro de tolerancia.');
})().catch((err) => { console.error('ERROR:', err); process.exit(1); });
