# Reglas de Desarrollo del Proyecto y Tienda Online

Todas las inteligencias artificiales, desarrolladores o agentes trabajando en este repositorio **DEBEN** adherirse de forma incondicional a las siguientes reglas para mantener la estabilidad del SaaS actual y asegurar la escalabilidad.

## 1. Aislamiento del Nuevo Módulo "Tienda Online"

El desarrollo de la nueva característica de "Tienda Online" (el catálogo web al que accederán los clientes finales) es un **Frontend separado**.

- **Regla Estricta de Carpeta:** TODO el código, subcarpetas, componentes, hooks, vistas y dependencias del frontal de la tienda, deben estar ubicados *única y exclusivamente* dentro de la carpeta `/tienda_online` en la raíz del proyecto.
- **Cero Modificaciones Invasivas:** El código del frontend de la tienda NO debe modificar, importar o depender de archivos HTML/Jinja/Javascript que se utilicen en el sistema backoffice principal (`sistema_silvio_cel`), salvo para consumir las APIs expuestas obligatorias y exclusivas.
- **Interacción Exclusiva:** `tienda_online` solo habla con el sistema "padre" mediante llamadas a URLs de la API REST (`/api/tienda/...`).

## 2. Regla de "Clean Code" (Longitud de Archivos)

Con el fin de asegurar mantenibilidad y evitar la aparición de "Componentes Dios" (God Components):

- **Límite Máximo de Código:** NINGÚN archivo dentro del desarrollo (especialmente dentro de la estructura general y la carpeta `tienda_online`) podrá exceder el límite rígido de **600 líneas de código**.
- **Refactorización Activa (Divide y Vencerás):** Si notas que, al seguir una instrucción o agregar una funcionalidad, un archivo va a estar cerca o va a romper dicho límite, es tu obligación **DIVIDIR EL CÓDIGO** en otro componente secundario, archivo de utilidad (`utils`), custom hook (`hooks/`) o servicio (`services/`).
- **Subcarpetas Lógicas:** Debes hacer uso intensivo y pragmático de subcarpetas jerárquicas dentro de la arquitectura de Node/React. Si estás creando un botón complejo, envuélvelo en `components/ui/` y no en el archivo madre principal.

## 3. Reutilización Antes de Duplicar

- **Búsqueda Obligatoria:** Antes de crear una nueva función, componente, hook, servicio o utilidad, debes verificar si ya existe una implementación que resuelva total o parcialmente la necesidad.
- **Reutilización Responsable:** Si ya existe una pieza reutilizable, debe preferirse su uso o una extensión segura de la misma antes que duplicar lógica.
- **No Reutilización Forzada:** NO debes reutilizar o modificar una función existente si eso mezcla responsabilidades, rompe compatibilidad, agrega condicionales específicos de un solo caso o vuelve más difícil entender el código.
- **Patrón Correcto en Caso de Duda:** Si existe lógica parecida pero no encaja limpiamente, extrae la parte común a una utilidad compartida o crea un adaptador delgado; no dupliques ni deformes una función sana para un caso nuevo.

## 4. Manejo Tecnológico Backend

Cualquier desarrollo en el backend de Python/Flask (`sistema_silvio_cel`) no debe romper los modelos pre-existentes de los clientes. Los nuevos campos siempre deben tener valores o alternativas por defecto (Default) o soportar Nulos.
Todos los datos visuales de la tienda multi-tenant están atados semánticamente al `cliente_id`. No hay escapes trans-cliente bajo ninguna circunstancia.
