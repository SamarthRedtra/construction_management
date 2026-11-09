# Copyright (c) 2026, Construction Management
# License: MIT

import base64
import mimetypes
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

import frappe
from frappe import _
from frappe.core.doctype.file.utils import find_file_by_url


def get_report_pdf_options(orientation="Landscape"):
	"""Options for Chromium Page.printToPDF (orientation + margins)."""
	return {
		"orientation": orientation,
		"margin-top": "10mm",
		"margin-bottom": "10mm",
		"margin-left": "8mm",
		"margin-right": "8mm",
	}


def get_report_pdf(html, orientation="Landscape"):
	"""Render report HTML to PDF via Chrome — avoids wkhtmltopdf on email/SOA paths."""
	from frappe.utils.pdf import get_chrome_pdf

	pdf = get_chrome_pdf(
		print_format=None,
		html=inline_file_images(html),
		options=get_report_pdf_options(orientation=orientation),
		output=None,
		pdf_generator="chrome",
	)
	if not pdf:
		frappe.throw(_("PDF generation failed (Chrome)."))
	return pdf


def inline_file_images(html):
	"""Embed file-backed images as base64 so the PDF engine does not fetch them over HTTP."""
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
