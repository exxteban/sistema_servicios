'use strict';

const express = require('express');

// Las librerías de TIPS se publican como módulos ESM con export default; bajo
// CommonJS quedan en `.default`.
const xmlgenLib = require('facturacionelectronicapy-xmlgen');
const xmlgen = xmlgenLib.default || xmlgenLib;
const xmlsignLib = require('facturacionelectronicapy-xmlsign');
const xmlsign = xmlsignLib.default || xmlsignLib;
const qrgenLib = require('facturacionelectronicapy-qrgen');
const qrgen = qrgenLib.default || qrgenLib;
const setapiLib = require('facturacionelectronicapy-setapi');
const setapi = setapiLib.default || setapiLib;

const app = express();
app.use(express.json({ limit: '4mb' }));

const PORT = process.env.PORT || 3010;
// Sin autenticación propia: expone el certificado del emisor a quien lo
// alcance. Sólo el Flask local debe poder hablarle; para exponerlo a otra
// máquina, ponelo detrás de un proxy con auth, no cambies este bind.
const HOST = process.env.HOST || '127.0.0.1';

app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'sifen-xmlgen' });
});

// xmlgen escribe siempre <cTipReg/>, haya régimen o no: su guarda es
// `typeof params['tipoRegimen'] != undefined`, que en JS da true siempre
// (typeof devuelve un string, nunca el valor undefined). SIFEN rechaza el
// elemento vacío con 0160 "El valor del elemento: cTipReg es invalido", y
// como el emisor común no tiene régimen especial, eso tumba toda factura.
// Se quita acá, antes de firmar: después la firma cubre el documento y
// tocar el XML la invalida. Si el emisor sí declara un régimen, el elemento
// viene con valor y no se toca.
function quitarTipoRegimenVacio(xml) {
  return xml
    .replace(/<cTipReg\s*\/>/g, '')
    .replace(/<cTipReg>\s*<\/cTipReg>/g, '');
}

// xmlgen redondea el agregado de **cada tasa** a guaraní entero por separado y
// recién después suma los redondeados para el total. SIFEN, en cambio,
// recalcula desde los valores de cada ítem, que viajan con 8 decimales, y
// tolera menos de medio guaraní de diferencia.
//
// Con una sola tasa no hay problema: un único redondeo nunca se aleja más de
// 0,5. Con 5% y 10% en la misma venta, los dos redondeos pueden empujar para
// el mismo lado y el total queda hasta 1 guaraní arriba del real. Dos rechazos
// del 2026-09-22, el mismo defecto en dos familias de campos:
//
//   DE 0000016 → `2377 Cálculo del total de la base gravada del IVA incorrecto`
//                dTBasGraIVA declarado 463031, real 463030,303
//   DE 0000017 → `2371 Cálculo de la liquidación total del IVA incorrecto`
//                dTotIVA declarado 43356, real 43355,394
//
// **No existe una solución en enteros.** Con bases reales de 286666,67 y
// 176363,64, los únicos enteros a menos de 0,5 de cada una son 286667 y
// 176364, y su suma (463031) queda a 0,70 del total real: cualquier
// combinación falla una validación o la otra. Por eso los seis campos van con
// precisión completa, igual que los valores por ítem que SIFEN ya aceptó en
// los DE aprobados.
//
// Los subtotales por tasa (`dSub5`/`dSub10`) NO entran: son base + IVA, que da
// el importe del ítem exacto, sin resto. `dLiqTotIVA5`/`dLiqTotIVA10` tampoco:
// van en 0 porque son de operaciones por comisión, y SIFEN los aceptó así.
//
// Se toca sólo el documento de tasas mezcladas: el de tasa única ya viene
// emitiendo aprobado con enteros y no hay por qué moverlo.
function corregirTotalesIVA(xml) {
  const acumulado = {
    5: { base: 0, iva: 0 },
    10: { base: 0, iva: 0 },
  };
  let vistas = 0;
  for (const bloque of xml.match(/<gCamIVA>[\s\S]*?<\/gCamIVA>/g) || []) {
    const leer = (tag) => (bloque.match(new RegExp('<' + tag + '>([^<]*)</' + tag + '>')) || [])[1];
    const tasa = leer('dTasaIVA');
    const base = leer('dBasGravIVA');
    const iva = leer('dLiqIVAItem');
    if (acumulado[tasa] === undefined || base === undefined) continue;
    acumulado[tasa].base += parseFloat(base) || 0;
    acumulado[tasa].iva += parseFloat(iva) || 0;
    vistas += 1;
  }
  if (!vistas || acumulado[5].base <= 0 || acumulado[10].base <= 0) return xml;

  // `Number(x.toFixed(8))` deja los ceros de más afuera: un agregado que da
  // entero se escribe entero, igual que los que escribe la librería.
  const escribir = (valor) => String(Number(valor.toFixed(8)));
  const reemplazar = (texto, tag, valor) =>
    texto.replace(new RegExp('<' + tag + '>[^<]*</' + tag + '>'), '<' + tag + '>' + valor + '</' + tag + '>');

  const campos = [
    ['dBaseGrav5', acumulado[5].base],
    ['dBaseGrav10', acumulado[10].base],
    ['dTBasGraIVA', acumulado[5].base + acumulado[10].base],
    ['dIVA5', acumulado[5].iva],
    ['dIVA10', acumulado[10].iva],
    ['dTotIVA', acumulado[5].iva + acumulado[10].iva],
  ];
  return campos.reduce((texto, [tag, valor]) => reemplazar(texto, tag, escribir(valor)), xml);
}

app.post('/generar', async (req, res) => {
  const { params, data, options } = req.body || {};
  if (!params || !data) {
    return res.status(400).json({ error: 'Se requieren "params" y "data".' });
  }
  try {
    const generado = await xmlgen.generateXMLDE(params, data, options || { defaultValues: true });
    const xml = corregirTotalesIVA(quitarTipoRegimenVacio(generado));
    res.json({ xml });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(422).json({ error: mensaje });
  }
});

app.post('/firmar', async (req, res) => {
  const { xml, certPath, password } = req.body || {};
  if (!xml || !certPath) {
    return res.status(400).json({ error: 'Se requieren "xml" y "certPath".' });
  }
  try {
    // signByNodeJS=true: firma en Node puro, sin depender de openssl/java.
    const firmado = await xmlsign.signXML(xml, certPath, password || '', true);
    res.json({ xml: firmado });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(422).json({ error: mensaje });
  }
});

app.post('/qr', async (req, res) => {
  const { xml, idCSC, csc, env } = req.body || {};
  if (!xml || !idCSC || !csc) {
    return res.status(400).json({ error: 'Se requieren "xml" (firmado), "idCSC" y "csc".' });
  }
  try {
    const xmlConQR = await qrgen.generateQR(xml, idCSC, csc, env || 'test');
    res.json({ xml: xmlConQR });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(422).json({ error: mensaje });
  }
});

// Envío a SIFEN (siRecepDE síncrono). Requiere certificado real habilitado por
// la DNIT y TLS mutuo, por eso recién se puede probar con un cert real.
app.post('/enviar', async (req, res) => {
  const { xml, certPath, password, env, id } = req.body || {};
  if (!xml || !certPath) {
    return res.status(400).json({ error: 'Se requieren "xml" (firmado) y "certPath".' });
  }
  try {
    const respuesta = await setapi.recibe(
      id || Date.now(), xml, env || 'test', certPath, password || '', { timeout: 90000 }
    );
    res.json({ respuesta });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(502).json({ error: mensaje });
  }
});

// Envío por lote (siRecepLoteDE, asíncrono). La librería arma el rLoteDE, lo
// comprime en zip y lo manda en base64; SIFEN sólo contesta que lo recibió
// (0300) y el número de lote (`dProtConsLote`). El resultado de cada DE se
// pide después con /consultar-lote. Como en /enviar, cada XML tiene que traer
// la declaración `<?xml ...?>` en su primera línea: la librería la corta.
app.post('/enviar-lote', async (req, res) => {
  const { xmls, certPath, password, env, id } = req.body || {};
  if (!Array.isArray(xmls) || !xmls.length || !certPath) {
    return res.status(400).json({ error: 'Se requieren "xmls" (lista de DE firmados) y "certPath".' });
  }
  try {
    const respuesta = await setapi.recibeLote(
      id || Date.now(), xmls, env || 'test', certPath, password || '',
      { timeout: 90000, debug: process.env.SIFEN_DEBUG === '1' }
    );
    res.json({ respuesta });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(502).json({ error: mensaje });
  }
});

// Resultado de un lote (siConsLoteDE): 0361 sigue en proceso, 0362 concluido
// con el resultado de cada DE, 0364 consulta fuera de las 48h.
app.post('/consultar-lote', async (req, res) => {
  const { numeroLote, certPath, password, env, id } = req.body || {};
  if (!numeroLote || !certPath) {
    return res.status(400).json({ error: 'Se requieren "numeroLote" y "certPath".' });
  }
  try {
    const respuesta = await setapi.consultaLote(
      id || Date.now(), numeroLote, env || 'test', certPath, password || '',
      { timeout: 90000, debug: process.env.SIFEN_DEBUG === '1' }
    );
    res.json({ respuesta });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(502).json({ error: mensaje });
  }
});

// Cancelación de un DE aprobado (evento siRecepEvento, tipoEvento=1). Genera el
// XML del evento, lo firma como evento (rEve) y lo envía. Requiere cert real.
app.post('/cancelar', async (req, res) => {
  const { params, cdc, motivo, certPath, password, env, id, fechaFirma } = req.body || {};
  if (!params || !cdc || !motivo || !certPath) {
    return res.status(400).json({ error: 'Se requieren "params", "cdc", "motivo" y "certPath".' });
  }
  try {
    const idEvento = id || Date.now();
    // dFecFirma lo escribe xmlgen con `new Date()` y lo formatea con getHours(),
    // o sea con la zona horaria **de este proceso**, y lo manda sin offset. En un
    // servidor en UTC el evento sale firmado tres horas en el futuro y SIFEN lo
    // rechaza con un error genérico. Flask manda la hora de Paraguay ya resuelta;
    // sin offset a propósito, para que `new Date()` la lea como hora local y la
    // escriba tal cual.
    const evento = { cdc, motivo };
    if (fechaFirma) evento.fechaFirmaDigital = fechaFirma;
    const xml = await xmlgen.generateXMLEventoCancelacion(idEvento, params, evento);
    const firmado = await xmlsign.signXMLEvento(xml, certPath, password || '', true);
    // SIFEN_DEBUG=1 hace que setapi imprima el SOAP exacto que POSTea y la
    // respuesta cruda. Es la única forma de ver el payload real cuando SIFEN
    // contesta "Error Inesperado" sin decir nada más.
    const respuesta = await setapi.evento(
      idEvento, firmado, env || 'test', certPath, password || '',
      { timeout: 90000, debug: process.env.SIFEN_DEBUG === '1' }
    );
    res.json({ respuesta, xml: firmado });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(502).json({ error: mensaje });
  }
});

// Inutilización de un rango de números quemados (evento siRecepEvento,
// tipoEvento=2). No es una cancelación: el DE nunca llegó a SIFEN, así que no
// hay CDC ni nada que dar de baja. Lo que se informa es que esos números del
// timbrado no se van a usar, para que el correlativo no quede con un hueco
// inexplicado. `data` lleva timbrado/establecimiento/punto/desde/hasta/
// tipoDocumento/motivo; xmlgen valida cada uno y tira un Error legible.
app.post('/inutilizar', async (req, res) => {
  const { params, data, certPath, password, env, id, fechaFirma } = req.body || {};
  if (!params || !data || !certPath) {
    return res.status(400).json({ error: 'Se requieren "params", "data" y "certPath".' });
  }
  try {
    const idEvento = id || Date.now();
    // Mismo problema de zona horaria que en /cancelar: Flask manda la hora de
    // Paraguay ya resuelta y sin offset, para que `new Date()` la lea local.
    const evento = Object.assign({}, data);
    if (fechaFirma) evento.fechaFirmaDigital = fechaFirma;
    const xml = await xmlgen.generateXMLEventoInutilizacion(idEvento, params, evento);
    const firmado = await xmlsign.signXMLEvento(xml, certPath, password || '', true);
    const respuesta = await setapi.evento(
      idEvento, firmado, env || 'test', certPath, password || '',
      { timeout: 90000, debug: process.env.SIFEN_DEBUG === '1' }
    );
    res.json({ respuesta, xml: firmado });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(502).json({ error: mensaje });
  }
});

// Consulta de estado de un DE por CDC (siConsDE).
app.post('/consultar', async (req, res) => {
  const { cdc, certPath, password, env, id } = req.body || {};
  if (!cdc || !certPath) {
    return res.status(400).json({ error: 'Se requieren "cdc" y "certPath".' });
  }
  try {
    const respuesta = await setapi.consulta(
      id || Date.now(), cdc, env || 'test', certPath, password || '', { timeout: 90000 }
    );
    res.json({ respuesta });
  } catch (err) {
    const mensaje = err && err.message ? err.message : String(err);
    res.status(502).json({ error: mensaje });
  }
});

// Sólo levanta el servidor cuando se ejecuta como programa. Requerido desde
// otro archivo (`test_bases_gravadas.js`) exporta las funciones y no escucha,
// así la prueba usa la función de verdad y no una copia que se desactualiza.
if (require.main === module) {
  app.listen(PORT, HOST, () => {
    console.log(`sifen-service (xmlgen+xmlsign) escuchando en http://${HOST}:${PORT}`);
  });
}

module.exports = { app, quitarTipoRegimenVacio, corregirTotalesIVA };
