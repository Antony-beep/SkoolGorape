import argparse
import json
import os
import sys
import logging
from urllib.parse import urlparse, urlunparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("skool_downloader.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)

from scrapling_fetcher import SkoolFetcher
from course_parser import CourseParser
from video_downloader import VideoDownloader

BANNER = r"""
   ____ _                _  ____                             
  / ___| | _____   ___  | |/ ___|  ___  _ __ __ _ _ __   ___ 
 \___ \| |/ / _ \ / _ \ | | |  _  / _ \| '__/ _` | '_ \ / _ \
  ___) |   < (_) | (_) || | |_| || (_) | | | (_| | |_) |  __/
 |____/|_|\_\___/ \___/ |_|\____| \___/|_|  \__,_| .__/ \___|
                                                 |_|         
                 Skool Video Downloader v2.5
          Soporte Multi-Nivel de Módulos y Submódulos
"""

def clean_base_url(url: str) -> str:
    """Removes query parameters like ?md=... to get the base classroom URL."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def main():
    print(BANNER)
    parser = argparse.ArgumentParser(description="Sistema de Scraping y Descarga de Cursos de Skool.com")
    parser.add_argument("--url", "-u", type=str, help="URL del aula / curso de Skool.com a descargar")
    parser.add_argument("--cookies", "-c", type=str, help="Ruta al archivo de cookies (JSON o Netscape .txt)")
    parser.add_argument("--output", "-o", type=str, default="downloads", help="Directorio destino para los videos (por defecto: downloads)")
    parser.add_argument("--wait", "-w", type=int, default=3, help="Tiempo de espera en segundos para carga de página")
    parser.add_argument("--headless", action="store_true", default=True, help="Ejecutar el navegador en modo headless (oculto)")
    parser.add_argument("--dump-manifest", type=str, help="Ruta opcional para guardar el manifiesto estructurado en formato JSON")

    args = parser.parse_args()

    target_url = args.url
    if not target_url:
        print("[i] Sugerencia: Puedes pasar la URL mediante la opción --url='https://www.skool.com/...'")
        target_url = input("Ingresa la URL del curso de Skool: ").strip()

    if not target_url:
        logging.error("No se proporcionó ninguna URL. Saliendo...")
        sys.exit(1)

    logging.info(f"Iniciando procesamiento para: {target_url}\n")

    fetcher = SkoolFetcher(cookies_path=args.cookies, wait_seconds=args.wait, headless=args.headless)
    parser_engine = CourseParser()

    # Step 1: Fetch initial page HTML
    try:
        html_content = fetcher.fetch_page_html(target_url)
    except Exception as e:
        logging.error(f"Error al obtener la página web: {e}")
        sys.exit(1)

    # Step 2: Parse course metadata and recursive module list
    logging.info("Analizando estructura inicial del curso (Módulos y Submódulos)...")
    parsed_initial = parser_engine.parse_course(html_content)
    
    course_title = parsed_initial.get("course_title", "Skool_Course")
    group_id = parsed_initial.get("group_id", "")
    modules_list = parsed_initial.get("modules_list", [])

    logging.info(f"Curso detectado: '{course_title}' con {len(modules_list)} lección(es) / submódulo(s).")

    # Fetch Calendar Data
    group_slug = urlparse(target_url).path.split('/')[1]
    calendar_url = f"https://www.skool.com/{group_slug}/calendar"
    logging.info(f"Obteniendo datos del calendario desde {calendar_url}...")
    calendar_map = {}
    try:
        cal_html = fetcher.fetch_page_html(calendar_url)
        cal_data = parser_engine.extract_next_data(cal_html)
        if cal_data:
            events = cal_data.get("props", {}).get("pageProps", {}).get("events", [])
            for ev in events:
                title = ev.get("metadata", {}).get("title")
                start_time = ev.get("startTime")
                if title and start_time:
                    date_str = start_time.split('T')[0]
                    calendar_map[title.strip().lower()] = date_str
            logging.info(f"Se encontraron {len(calendar_map)} eventos únicos en el calendario.")
    except Exception as e:
        logging.warning(f"Error al obtener el calendario: {e}")

    base_url = clean_base_url(target_url)
    final_modules: dict = {}

    # Step 3: Iterate modules to fetch video URLs, descriptions & resources for each lesson
    for idx, mod_info in enumerate(modules_list, start=1):
        mod_id = mod_info.get("id")
        original_mod_title = mod_info.get("title", f"Modulo_{idx}")
        
        # Match calendar date
        mod_date = None
        for cal_title, c_date in calendar_map.items():
            if cal_title in original_mod_title.lower() or original_mod_title.lower() in cal_title:
                mod_date = c_date
                break
                
        mod_title = f"{original_mod_title} - {mod_date}" if mod_date else original_mod_title

        set_title = mod_info.get("set_title")
        video_url = mod_info.get("url")
        description = mod_info.get("description", "")
        resources = mod_info.get("resources", [])

        # If video_url or description is missing from initial payload, fetch specific module page
        if (not video_url or not description) and mod_id:
            mod_url = f"{base_url}?md={mod_id}"
            set_str = f" [{set_title}]" if set_title else ""
            logging.info(f"[*] Obteniendo datos completos para [{idx}/{len(modules_list)}]{set_str}: {mod_title}...")
            try:
                mod_html = fetcher.fetch_page_html(mod_url)
                next_data = parser_engine.extract_next_data(mod_html)
                if next_data:
                    page_props = next_data.get("props", {}).get("pageProps", {})
                    if not video_url:
                        video_url = parser_engine.extract_video_from_page_props(page_props)
                    
                    # Recursive search in module page for full description and resources
                    def find_mod_data(node):
                        nonlocal video_url, description, resources
                        if not isinstance(node, dict):
                            return
                        c_info = node.get("course", {})
                        if c_info.get("id") == mod_id:
                            meta = c_info.get("metadata", {})
                            if not video_url and meta.get("videoLink"):
                                video_url = parser_engine.normalize_video_url(meta.get("videoLink"))
                            if not description and meta.get("desc"):
                                description = parser_engine.parse_description_text(meta.get("desc"))
                            if not resources and meta.get("resources"):
                                res_raw = meta.get("resources")
                                if isinstance(res_raw, str):
                                    try:
                                        resources = json.loads(res_raw)
                                    except Exception:
                                        pass
                                elif isinstance(res_raw, list):
                                    resources = res_raw
                        for child in node.get("children", []):
                            find_mod_data(child)

                    find_mod_data(page_props.get("course", {}))
            except Exception as e:
                logging.warning(f"No se pudo obtener el submódulo {mod_id}: {e}")

        module_key = f"{idx:02d}_{mod_title}"
        final_modules[module_key] = [{
            "title": mod_title,
            "set_title": set_title,
            "url": video_url,
            "description": description,
            "resources": resources
        }]

    structured_course = {
        "course_title": course_title,
        "group_id": group_id,
        "modules": final_modules
    }

    total_lessons = sum(len(l) for l in final_modules.values())
    logging.info(f"\nProcesamiento completo: {len(final_modules)} lección(es) / submódulo(s) estructurados.")

    if getattr(args, "dump_manifest", None):
        manifest_path = args.dump_manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(structured_course, f, indent=4, ensure_ascii=False)
        logging.info(f"Manifiesto guardado en: {manifest_path}")

    # Step 4: Download all videos, descriptions, and resources
    downloader = VideoDownloader(output_dir=args.output, cookies_path=args.cookies)
    downloader.download_course(structured_course)

if __name__ == "__main__":
    main()
