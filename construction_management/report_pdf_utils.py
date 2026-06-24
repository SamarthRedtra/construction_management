# Copyright (c) 2026, Construction Management
# License: MIT

import base64
import mimetypes
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

import frappe
from frappe.core.doctype.file.utils import find_file_by_url
from frappe.utils import get_url


def get_report_pdf_options(orientation="Landscape"):
	"""PDF options used by Frappe report_to_pdf for reliable wkhtmltopdf rendering."""
	return {
		"orientation": orientation,
		"proxy": "http://0.0.0.0:0",
		"bypass-proxy-for": urlparse(get_url(allow_header_override=False)).hostname,
		"load-error-handling": "ignore",
	}


def inline_file_images(html):
	"""Embed file-backed images as base64 so wkhtmltopdf does not fetch them over HTTP."""
	if not html:
		return html

	soup = BeautifulSoup(html, "html.parser")
	changed = False

	for img in soup.find_all("img"):
		src = img.get("src")
		if not src or src.startswith("data:"):
			continue

		parsed_url = urlparse(src)
		path = parsed_url.path
		query = parse_qs(parsed_url.query)
		mime_type = mimetypes.guess_type(path)[0]
		if not mime_type or not mime_type.startswith("image/"):
			continue

		filename = (query.get("fid") and query["fid"][0]) or None
		file = find_file_by_url(path, name=filename)
		if not file or not file.is_downloadable():
			continue

		try:
			b64_encoded_image = base64.b64encode(file.get_content()).decode()
			img["src"] = f"data:{mime_type};base64,{b64_encoded_image}"
			changed = True
		except Exception:
			frappe.logger("pdf").error(
				"Failed to inline image for PDF: %s", path, exc_info=True
			)

	return str(soup) if changed else html
