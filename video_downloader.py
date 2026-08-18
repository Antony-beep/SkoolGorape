import os
import re
import json
import tempfile
import subprocess
import sys
import logging
import requests
from typing import Optional, Dict, List, Any

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None

class VideoDownloader:
    """
    Handles downloading videos (using yt-dlp merged with ffmpeg), 
    saving descriptions into .txt files, and downloading PDF resources via Skool API.
    Organizes everything neatly into subdirectories supporting Sets and Submodules.
    """

    def __init__(self, output_dir: str = "downloads", cookies_path: Optional[str] = None):
        self.output_dir = output_dir
        self.cookies_path = cookies_path
        self._temp_cookies_file = None
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitizes string to make it safe for folder and file names across Windows/OSX/Linux."""
        cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
        cleaned = cleaned.strip('. ')
        return cleaned if cleaned else "Sin_Titulo"

    def _get_netscape_cookies_path(self) -> Optional[str]:
        """Returns path to a Netscape-formatted cookies file. Converts JSON if necessary."""
        if not self.cookies_path or not os.path.exists(self.cookies_path):
            return None

        with open(self.cookies_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()

        if not (content.startswith("[") and content.endswith("]")):
            return self.cookies_path

        try:
            json_cookies = json.loads(content)
            temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", encoding="utf-8")
            temp_file.write("# Netscape HTTP Cookie File\n")
            temp_file.write("# Generated automatically for yt-dlp\n\n")

            for c in json_cookies:
                if not isinstance(c, dict):
                    continue
                domain = c.get("domain") or c.get("host") or ".skool.com"
                if not domain.startswith(".") and domain.count(".") > 1:
                    domain = "." + domain
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure") or c.get("isSecure") == 1 else "FALSE"
                expiry = int(c.get("expirationDate") or c.get("expiry") or 0)
                name = c.get("name", "")
                val = c.get("value", "")

                if name:
                    temp_file.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{val}\n")

            temp_file.close()
            self._temp_cookies_file = temp_file.name
            return temp_file.name
        except Exception as e:
            logging.warning(f"Error convirtiendo cookies JSON a Netscape: {e}")
            return self.cookies_path

    def download_course(self, course_data: Dict[str, Any]) -> None:
        """
        Downloads all lessons, descriptions, and resources in the course structure.
        """
        course_title = self.sanitize_filename(course_data.get("course_title", "Skool_Course"))
        modules = course_data.get("modules", {})

        total_lessons = sum(len(lessons) for lessons in modules.values())
        logging.info(f"Iniciando descarga para la clase '{course_title}' ({total_lessons} lecciones en total)...")

        current_index = 0
        for mod_key, lessons in modules.items():
            current_index += 1
            for lesson in lessons:
                set_title = lesson.get("set_title")
                mod_title = lesson.get("title", f"Leccion_{current_index}")
                
                # Format directory path with Set title if present
                if set_title:
                    clean_set = self.sanitize_filename(set_title)
                    clean_mod = f"{current_index:02d}_{self.sanitize_filename(mod_title)}"
                    module_dir = os.path.join(self.output_dir, course_title, clean_set, clean_mod)
                else:
                    clean_mod = f"{current_index:02d}_{self.sanitize_filename(mod_title)}"
                    module_dir = os.path.join(self.output_dir, course_title, clean_mod)

                os.makedirs(module_dir, exist_ok=True)

                logging.info(f"\n==================================================")
                set_info_str = f" [{set_title}]" if set_title else ""
                logging.info(f"📁 [{current_index}/{total_lessons}] Procesando{set_info_str}: {mod_title}")
                logging.info(f"   Carpeta: {module_dir}")
                logging.info(f"==================================================")

                video_url = lesson.get("url")
                description = lesson.get("description", "")
                resources = lesson.get("resources", [])

                # 1. Save Description .txt file
                if description:
                    desc_filename = os.path.join(module_dir, "descripcion.txt")
                    try:
                        with open(desc_filename, "w", encoding="utf-8") as df:
                            df.write(f"--- {mod_title} ---\n\n{description}\n")
                        logging.info(f"   📄 Descripción guardada en 'descripcion.txt'")
                    except Exception as de:
                        logging.warning(f"   [!] Error guardando descripción: {de}")

                # 2. Download PDF / Attachment resources
                if resources:
                    logging.info(f"   📎 Descargando {len(resources)} recurso(s) adjunto(s)...")
                    self._download_resources(resources, module_dir)

                # 3. Download Video (Merged Video + Audio)
                if video_url:
                    logging.info(f"   ▶ Descargando video desde: {video_url[:75]}...")
                    self._download_single_video(video_url, module_dir, "video")
                else:
                    logging.warning(f"   [!] No hay URL de video activa para esta lección.")

        logging.info(f"\n[🎉] ¡Descarga completa! Todos los archivos organizados en '{os.path.abspath(os.path.join(self.output_dir, course_title))}'!")
        
        if self._temp_cookies_file and os.path.exists(self._temp_cookies_file):
            try:
                os.remove(self._temp_cookies_file)
            except Exception:
                pass

    def _download_resources(self, resources: List[Dict[str, Any]], target_dir: str) -> None:
        """Downloads PDF or attachment files for a lesson into its directory via Skool API."""
        cookies_dict = {}
        auth_token = ""
        if self.cookies_path and os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, "r", encoding="utf-8", errors="ignore") as cf:
                    c_data = json.load(cf)
                    for c in c_data:
                        if isinstance(c, dict) and "name" in c and "value" in c:
                            cookies_dict[c["name"]] = c["value"]
                            if c["name"] == "auth_token":
                                auth_token = c["value"]
            except Exception:
                pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://www.skool.com/"
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        for res in resources:
            if not isinstance(res, dict):
                continue
            file_id = res.get("file_id")
            file_name = res.get("file_name") or res.get("title") or "Adjunto.pdf"
            clean_name = self.sanitize_filename(file_name)
            if not clean_name.lower().endswith(".pdf") and not "." in clean_name:
                clean_name += ".pdf"

            out_path = os.path.join(target_dir, clean_name)
            if not file_id:
                continue

            api_url = f"https://api2.skool.com/files/{file_id}/download-url?expire=28800"
            success = False

            try:
                if HAS_CURL_CFFI:
                    r = cffi_requests.post(api_url, headers=headers, cookies=cookies_dict, json={}, impersonate="chrome120", timeout=15)
                else:
                    r = requests.post(api_url, headers=headers, cookies=cookies_dict, json={}, timeout=15)

                if r.status_code == 200 and r.text:
                    download_url = r.text.strip().strip('"')
                    if download_url.startswith("http"):
                        pdf_res = requests.get(download_url, headers={"User-Agent": headers["User-Agent"]}, timeout=30)
                        if pdf_res.status_code == 200 and len(pdf_res.content) > 200:
                            with open(out_path, "wb") as pf:
                                pf.write(pdf_res.content)
                            logging.info(f"      OK: Adjunto PDF descargado exitosamente: '{clean_name}'")
                            success = True
            except Exception as e:
                logging.warning(f"      [!] Excepción al descargar adjunto '{file_name}': {e}")

            if not success:
                logging.warning(f"      [!] No se pudo descargar el adjunto '{file_name}' (ID: {file_id})")

    def _download_single_video(self, video_url: str, target_dir: str, filename_prefix: str) -> None:
        """Invokes yt-dlp with ffmpeg to download and merge video and audio into a single MP4 file."""
        output_template = os.path.join(target_dir, f"{filename_prefix}.%(ext)s")

        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-o", output_template,
            "--referer", "https://www.skool.com/",
            "--merge-output-format", "mp4",
            "--no-warnings",
            "--no-mtime",
            video_url
        ]

        if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
            cmd.extend(["--ffmpeg-location", FFMPEG_PATH])

        valid_cookies_file = self._get_netscape_cookies_path()
        if valid_cookies_file and os.path.exists(valid_cookies_file):
            cmd.extend(["--cookies", valid_cookies_file])

        try:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                logging.warning(f"yt-dlp finalizo con codigo {result.returncode} para {video_url[:60]}...")
            else:
                logging.info(f"   OK: Video descargado y unificado exitosamente en {target_dir}")
        except Exception as e:
            logging.error(f"Error ejecutando yt-dlp: {e}")
