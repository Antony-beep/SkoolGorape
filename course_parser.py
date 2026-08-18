import json
import re
from typing import List, Dict, Any, Optional

class CourseParser:
    """
    Parser for Skool classroom HTML and Next.js __NEXT_DATA__ payload.
    Supports multi-level courses with Sets, Submodules, and Lessons.
    """

    @staticmethod
    def extract_next_data(html_content: str) -> Optional[Dict[str, Any]]:
        """Extracts and parses the __NEXT_DATA__ JSON script tag from Skool HTML."""
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e:
                print(f"[!] Error al deserializar __NEXT_DATA__ JSON: {e}")
        return None

    @staticmethod
    def normalize_video_url(url: str) -> str:
        """Normalizes video links (Loom, YouTube, Vimeo, etc.)."""
        if not url:
            return ""
        
        if "loom.com" in url:
            loom_match = re.search(r'loom\.com/(?:share|embed)/([a-zA-Z0-9_-]+)', url)
            if loom_match:
                return f"https://www.loom.com/share/{loom_match.group(1)}"
        elif "youtube.com" in url or "youtu.be" in url:
            yt_match = re.search(r'(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
            if yt_match:
                return f"https://www.youtube.com/watch?v={yt_match.group(1)}"
        elif "vimeo.com" in url:
            vimeo_match = re.search(r'vimeo\.com/(?:video/)?([0-9]+)', url)
            if vimeo_match:
                return f"https://vimeo.com/{vimeo_match.group(1)}"
                
        return url.strip()

    @staticmethod
    def parse_description_text(desc_raw: Any) -> str:
        """Converts raw description (TipTap JSON or string) into readable plain text."""
        if not desc_raw:
            return ""
        
        if isinstance(desc_raw, str):
            if desc_raw.startswith("[v2]"):
                json_part = desc_raw[4:]
                try:
                    desc_data = json.loads(json_part)
                    return CourseParser._extract_text_from_tiptap(desc_data)
                except Exception:
                    return desc_raw.replace("[v2]", "").strip()
            return desc_raw.strip()
        elif isinstance(desc_raw, (list, dict)):
            return CourseParser._extract_text_from_tiptap(desc_raw)
        
        return str(desc_raw)

    @staticmethod
    def _extract_text_from_tiptap(node: Any) -> str:
        """Recursively extracts clean text from TipTap editor JSON structure."""
        text_parts = []

        if isinstance(node, dict):
            node_type = node.get("type")
            if node_type == "text" and "text" in node:
                text_parts.append(node.get("text", ""))
            elif node_type == "hardBreak":
                text_parts.append("\n")

            if "content" in node and isinstance(node["content"], list):
                for child in node["content"]:
                    text_parts.append(CourseParser._extract_text_from_tiptap(child))
                if node_type in ["paragraph", "heading", "bulletList", "listItem"]:
                    text_parts.append("\n")

        elif isinstance(node, list):
            for item in node:
                text_parts.append(CourseParser._extract_text_from_tiptap(item))

        raw_str = "".join(text_parts)
        # We preserve spaces and tabs, but collapse 3+ newlines into 2
        raw_str = re.sub(r'\n{3,}', '\n\n', raw_str)
        return raw_str.strip('\n')

    @staticmethod
    def extract_video_from_page_props(page_props: Dict[str, Any]) -> Optional[str]:
        """Extracts video URL (Loom/YT link or Mux stream URL) from a pageProps object."""
        video_obj = page_props.get("video")
        if isinstance(video_obj, dict) and video_obj.get("playbackId"):
            playback_id = video_obj.get("playbackId")
            token = video_obj.get("playbackToken")
            if token:
                return f"https://stream.mux.com/{playback_id}.m3u8?token={token}"
            return f"https://stream.mux.com/{playback_id}.m3u8"
        return None

    def parse_course(self, html_content: str) -> Dict[str, Any]:
        """
        Parses the course structure from HTML.
        Recursively extracts Sets, Submodules, Lessons, descriptions, resources, and video URLs.
        """
        next_data = self.extract_next_data(html_content)
        if not next_data:
            return self._fallback_regex_parse(html_content)

        page_props = next_data.get("props", {}).get("pageProps", {})
        course_tree = page_props.get("course", {})
        
        course_title = "Skool_Course"
        group_id = ""
        if isinstance(course_tree, dict):
            c_root = course_tree.get("course", {})
            group_id = c_root.get("groupId", "")
            metadata = c_root.get("metadata", {})
            if metadata.get("title"):
                course_title = metadata.get("title")
            elif metadata.get("name"):
                course_title = metadata.get("name")

        modules_list = []

        def walk_tree(node: Any, current_set: Optional[str] = None):
            if not isinstance(node, dict):
                return
            children = node.get("children", [])
            for child in children:
                if not isinstance(child, dict):
                    continue
                c_info = child.get("course", {})
                unit_type = c_info.get("unitType")
                metadata = c_info.get("metadata", {})
                title = metadata.get("title") or metadata.get("name") or c_info.get("name")
                mod_id = c_info.get("id")

                if unit_type == "set":
                    walk_tree(child, current_set=title)
                elif unit_type in ["module", "lesson"]:
                    video_link = metadata.get("videoLink")
                    video_url = self.normalize_video_url(video_link) if video_link else None

                    if page_props.get("selectedModule") == mod_id and not video_url:
                        active_video = self.extract_video_from_page_props(page_props)
                        if active_video:
                            video_url = active_video

                    desc_text = self.parse_description_text(metadata.get("desc"))
                    
                    resources_raw = metadata.get("resources")
                    resources_list = []
                    if resources_raw:
                        if isinstance(resources_raw, str):
                            try:
                                resources_list = json.loads(resources_raw)
                            except Exception:
                                pass
                        elif isinstance(resources_raw, list):
                            resources_list = resources_raw

                    modules_list.append({
                        "id": mod_id,
                        "title": title,
                        "set_title": current_set,
                        "url": video_url,
                        "description": desc_text,
                        "resources": resources_list,
                        "group_id": group_id
                    })

        walk_tree(course_tree)

        return {
            "course_title": course_title,
            "group_id": group_id,
            "modules_list": modules_list,
            "page_props": page_props
        }

    def _fallback_regex_parse(self, html_content: str, course_title: str = "Skool_Course") -> Dict[str, Any]:
        loom_pattern = r'https?://(?:www\.)?loom\.com/(?:share|embed)/[a-zA-Z0-9_-]+'
        yt_pattern = r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)[a-zA-Z0-9_-]{11}'
        
        found_urls = set()
        for match in re.finditer(loom_pattern, html_content):
            found_urls.add(self.normalize_video_url(match.group(0)))
        for match in re.finditer(yt_pattern, html_content):
            found_urls.add(self.normalize_video_url(match.group(0)))

        modules_list = [{"id": None, "title": f"Video_{idx+1}", "set_title": None, "url": url, "description": "", "resources": []} for idx, url in enumerate(found_urls)]
        return {
            "course_title": course_title,
            "group_id": "",
            "modules_list": modules_list
        }
