# sifen_service

Microservicio Node aislado que genera el XML de los documentos electrónicos
SIFEN usando las librerías de TIPS. El sistema Flask sólo lo consume por HTTP;
no comparten código.

Endpoints actuales:
- `POST /generar` (`xmlgen`) — arma el XML del DE.
- `POST /firmar` (`xmlsign`) — firma el XML con un `.p12`.
- `POST /qr` (`qrgen`) — agrega el nodo `gCamFuFD/dCarQR` (QR) al XML firmado.
- `POST /enviar` (`setapi`, siRecepDE) — envía el DE firmado a SIFEN (TLS mutuo).
- `POST /consultar` (`setapi`, siConsDE) — consulta el estado de un DE por CDC.

> **Probado end-to-end el 2026-09-20** contra el ambiente de TEST de SIFEN,
> con certificado real: generar → firmar → QR → enviar terminó en
> `0260 Autorización del DE satisfactoria`. Falta la primera emisión en
> producción.
>
> `/generar` no devuelve el XML tal cual lo arma `xmlgen`: le quita el
> elemento `<cTipReg/>` vacío, que la librería escribe siempre y SIFEN
> rechaza. Ver `../facturacion_electronica/DIAGNOSTICO_SIFEN.md`, que junta
> las trampas de estas librerías y los códigos de rechazo con su significado
> real.

## Requisitos

- Node.js 18 o superior.

## Instalar y levantar

```bash
cd sifen_service
npm install
npm start
```

Queda escuchando en `http://127.0.0.1:3010` (puerto configurable con `PORT`).
Por defecto sólo acepta conexiones desde la misma máquina: el servicio no
tiene autenticación propia y quien lo alcance puede firmar XML con el
certificado del emisor (pasando `certPath`) o enviar documentos a SIFEN en su
nombre. Si necesitás exponerlo a otra máquina, hacelo detrás de un proxy con
autenticación y recién ahí cambiá `HOST`; no lo publiques directo con
`HOST=0.0.0.0`.

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
