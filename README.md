# Skool Video Downloader & Scraper 🚀

Sistema automatizado en Python para hacer scraping y descargar de manera organizada todos los módulos y videos de un curso en la plataforma **Skool.com**.

Este proyecto combina la potencia de **[Scrapling](https://scrapling.readthedocs.io/en/latest/index.html)** (framework de scraping con evasión de anti-bots y parsers adaptativos) con las técnicas de inspección de estado Next.js (`__NEXT_DATA__`) y desacoplamiento de descargas provenientes de **[skool-video-downloader de Fx64b](https://github.com/Fx64b/skool-video-downloader)**.

---

## 🛠️ Características Principales

- 📡 **Scraping Sigiloso:** Integración con `Scrapling` (`StealthyFetcher`) para obtener el contenido sin ser bloqueado por protecciones anti-bot de Cloudflare.
- 🌳 **Recorrido de Módulos y Lecciones:** Extrae la jerarquía exacta del curso (**Curso -> Módulos / Sets -> Lecciones**) inspeccionando el JSON nativo de Next.js (`__NEXT_DATA__`).
- 🎥 **Soporte Multi-Plataforma de Video:** Extrae e identifica automáticamente enlaces de **Loom**, **YouTube**, **Vimeo** y reproductores integrados.
- 📁 **Organización Automática:** Descarga los videos organizados en carpetas ordenadas por número y título del módulo/lección:
  ```text
  downloads/
  └── Nombre_Del_Curso/
      ├── 01_Modulo_Introduccion/
      │   ├── 01_Bienvenida.mp4
      │   └── 02_Instrucciones.mp4
      └── 02_Modulo_Avanzado/
          └── 01_Estrategia.mp4
  ```
- 🔑 **Autenticación mediante Cookies:** Soporta archivos de cookies tanto en formato JSON como en formato Netscape `.txt`.

---

## 📦 Requisitos e Instalación

### 1. Clonar o preparar el entorno
Asegúrate de tener Python 3.10 o superior instalado.

### 2. Instalar dependencias
Instala las bibliotecas necesarias ejecutando:
```bash
py -m pip install -r requirements.txt
```

*Nota: Asegúrate de tener instalado `yt-dlp` y que esté disponible en tu sistema o virtualenv.*

---

## 🚀 Modo de Uso

### 1. Uso Básico (Por Consola)
Puedes ejecutar el script principal indicando la URL del aula o curso de Skool:

```bash
py main.py --url "https://www.skool.com/tu-comunidad/classroom/tu-curso"
```

### 2. Uso con Autenticación por Cookies (Recomendado para cursos privados)
Si el curso requiere estar registrado e haber iniciado sesión en Skool:

1. Inicia sesión en Skool desde tu navegador.
2. Exporta tus cookies utilizando una extensión como **Cookie-Editor** (en formato JSON o Netscape TXT).
3. Guarda el archivo como `cookies.json` o `cookies.txt` en la carpeta del proyecto.
4. Ejecuta el script pasándole las cookies:

```bash
py main.py --url "https://www.skool.com/tu-comunidad/classroom/tu-curso" --cookies "cookies.json"
```

### 3. Opciones Adicionales de la Línea de Comandos

| Parámetro | Descripción |
| :--- | :--- |
| `--url`, `-u` | URL de la clase o aula de Skool.com a escanear y descargar. |
| `--cookies`, `-c` | Ruta al archivo de cookies (`cookies.json` o `cookies.txt`). |
| `--output`, `-o` | Carpeta de destino donde se guardarán los videos (Por defecto: `downloads`). |
| `--dump-manifest` | Guarda un archivo JSON con toda la estructura de módulos y lecciones encontradas. |

Ejemplo exportando el manifiesto del curso antes o durante la descarga:
```bash
py main.py --url "https://www.skool.com/comunidad/classroom/curso" --cookies "cookies.json" --dump-manifest "curso_estructura.json"
```

---

## 📂 Estructura del Código

- **`main.py`**: Interfaz CLI y orquestador principal del proceso.
- **`scrapling_fetcher.py`**: Motor de conexión y scraping basado en `Scrapling` que maneja las solicitudes sigilosas HTTP y la carga de cookies.
- **`course_parser.py`**: Lógica de extracción del JSON de Next.js (`__NEXT_DATA__`) y recorrido recursivo de los nodos de módulos y lecciones.
- **`video_downloader.py`**: Encargado de llamar a `yt-dlp` para descargar y nombrar los videos según su jerarquía.

---

## ⚠️ Descargo de Responsabilidad
Este sistema ha sido desarrollado únicamente con fines educativos y de respaldo personal. Asegúrate de respetar los términos de servicio de Skool.com y los derechos de autor del contenido al que accedes.
