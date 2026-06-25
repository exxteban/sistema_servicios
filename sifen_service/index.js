'use strict';

const express = require('express');

// Las librerías de TIPS se publican como módulos ESM con export default; bajo
// CommonJS quedan en `.default`.
const xmlgenLib = require('facturacionelectronicapy-xmlgen');
const xmlgen = xmlgenLib.default || xmlgenLib;
const xmlsignLib = require('facturacionelectronicapy-xmlsign');
const xmlsign = xmlsignLib.default || xmlsignLib;

const app = express();
app.use(express.json({ limit: '4mb' }));

const PORT = process.env.PORT || 3010;

app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'sifen-xmlgen' });
});

app.post('/generar', async (req, res) => {
  const { params, data, options } = req.body || {};
  if (!params || !data) {
    return res.status(400).json({ error: 'Se requieren "params" y "data".' });
  }
  try {
    const xml = await xmlgen.generateXMLDE(params, data, options || { defaultValues: true });
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

app.listen(PORT, () => {
  console.log(`sifen-service (xmlgen+xmlsign) escuchando en http://localhost:${PORT}`);
});
