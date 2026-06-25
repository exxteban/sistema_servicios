# sifen_service

Microservicio Node aislado que genera el XML de los documentos electrónicos
SIFEN usando las librerías de TIPS. El sistema Flask sólo lo consume por HTTP;
no comparten código.

Fase actual: **2c-1** — sólo genera el XML (no firma ni envía). La firma
(`xmlsign`) y el envío (`setapi`) se agregan más adelante, cuando exista el
certificado `.p12`.

## Requisitos

- Node.js 18 o superior.

## Instalar y levantar

```bash
cd sifen_service
npm install
npm start
```

Queda escuchando en `http://localhost:3010` (configurable con la variable
`PORT`).

## Probar

Verificar que está vivo:

```bash
curl http://localhost:3010/health
```

Generar un XML (enviá el JSON que muestra la "Vista previa" del sistema, con
las claves `params` y `data`):

```bash
curl -X POST http://localhost:3010/generar \
  -H "Content-Type: application/json" \
  -d @documento.json
```

Responde `{ "xml": "<rDE>...</rDE>" }` si está bien, o
`{ "error": "..." }` con el motivo si algún dato no cumple el esquema.

## Producción (systemd)

`npm start` se cae al cerrar la terminal. En el servidor se instala como
servicio systemd (arranca solo y se reinicia si se cae), igual que el sistema
Flask:

```bash
cd sifen_service/deploy
sudo SERVICE_USER=<usuario_del_sistema> PORT=3010 bash install_systemd.sh
```

Usá el **mismo usuario** con el que corre el sistema Flask (así, cuando se
agregue la firma, el servicio podrá leer el certificado).

Comandos útiles:

```bash
systemctl status sifen-service      # estado
journalctl -u sifen-service -f      # logs en vivo
systemctl restart sifen-service     # reiniciar tras actualizar el código
```

Cuando actualices el código (`git pull`), si cambiaron dependencias corré
`npm install --omit=dev` dentro de `sifen_service/` y después
`systemctl restart sifen-service`.

## Conexión con el sistema Flask

El Flask lo llama en la URL definida por la variable de entorno
`SIFEN_SERVICE_URL` (por defecto `http://localhost:3010`). En un servidor donde
ambos corren juntos, no hace falta configurar nada. Si el servicio no está
corriendo, el sistema lo informa sin romperse.
