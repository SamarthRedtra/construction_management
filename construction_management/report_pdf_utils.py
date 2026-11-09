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
		html=prepare_report_html_for_chrome(html),
		options=get_report_pdf_options(orientation=orientation),
		output=None,
		pdf_generator="chrome",
	)
	if not pdf:
		frappe.throw(_("PDF generation failed (Chrome)."))
	return pdf


def prepare_report_html_for_chrome(html):
	"""Inline images and flatten wkhtmltopdf header/footer hooks for Chrome.

	SOA templates use #header-html / #footer-html for wkhtmltopdf. Chrome's
	separate header/footer page merge often fails (KeyError on PDF stream), so
	keep letterhead/footer in the body instead.
	"""
	if not html:
		return html

	soup = BeautifulSoup(html, "html.parser")
	_flatten_print_header_footer(soup)
	_inline_file_images_in_soup(soup)
	return str(soup)


def _flatten_print_header_footer(soup):
	for tag in soup.find_all(id="header-html"):
		classes = [c for c in (tag.get("class") or []) if c != "hidden-pdf"]
		if "letter-head-block" not in classes:
			classes.append("letter-head-block")
		tag["class"] = classes
		del tag["id"]

	for tag in soup.find_all(id="footer-html"):
		classes = list(tag.get("class") or [])
		if "letter-head-footer-block" not in classes:
			classes.append("letter-head-footer-block")
		tag["class"] = classes
		del tag["id"]


def _inline_file_images_in_soup(soup):
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
		except Exception:
			frappe.logger("pdf").error(
				"Failed to inline image for PDF: %s", path, exc_info=True
			)


def inline_file_images(html):
	"""Embed file-backed images as base64 so the PDF engine does not fetch them over HTTP."""
	if not html:
		return html

	soup = BeautifulSoup(html, "html.parser")
	_inline_file_images_in_soup(soup)
	return str(soup)
