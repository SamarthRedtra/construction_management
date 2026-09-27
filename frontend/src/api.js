const METHOD_PREFIX = "construction_management.api.controlled_procurement."

export class ApiError extends Error {
	constructor(message, excType) {
		super(message)
		this.excType = excType
	}
}

function serverMessage(payload) {
	try {
		const messages = JSON.parse(payload._server_messages || "[]").map((raw) => JSON.parse(raw).message)
		if (messages.length) return messages.map(stripHtml).join("\n")
	} catch {
		/* fall through to exception text */
	}
	if (payload.exception) return payload.exception.split(":").slice(1).join(":").trim() || payload.exception
	return "Something went wrong."
}

function stripHtml(value) {
	const div = document.createElement("div")
	div.innerHTML = value || ""
	return div.textContent || ""
}

function encode(args) {
	const params = new URLSearchParams()
	for (const [key, value] of Object.entries(args)) {
		if (value === undefined || value === null) continue
		params.append(key, typeof value === "object" ? JSON.stringify(value) : value)
	}
	return params
}

export async function request(method, args = {}, type = "POST") {
	const headers = { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token || "" }
	let url = `/api/method/${method}`
	const options = { method: type, headers, credentials: "same-origin" }
	if (type === "GET") {
		const query = encode(args).toString()
		if (query) url += `?${query}`
	} else {
		headers["Content-Type"] = "application/json"
		options.body = JSON.stringify(args)
	}
	const response = await fetch(url, options)
	const payload = await response.json().catch(() => ({}))
	if (response.status === 403 && payload.session_expired) {
		window.location.href = `/login?redirect-to=${encodeURIComponent(window.location.pathname)}`
	}
	if (!response.ok || payload.exc_type) throw new ApiError(serverMessage(payload), payload.exc_type)
	return payload.message
}

// read endpoints are whitelisted as GET-only; everything else is POST
export function call(method, args = {}) {
	return request(METHOD_PREFIX + method, args, method.startsWith("get_") ? "GET" : "POST")
}

export async function linkSearch(doctype, txt = "", filters = {}) {
	const result = await request("frappe.desk.search.search_link", { doctype, txt, filters, page_length: 20 }, "POST")
	return result || []
}

export async function uploadFile(file) {
	const form = new FormData()
	form.append("file", file, file.name)
	form.append("is_private", "1")
	const response = await fetch("/api/method/upload_file", {
		method: "POST",
		headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token || "" },
		body: form,
		credentials: "same-origin",
	})
	const payload = await response.json().catch(() => ({}))
	if (!response.ok || payload.exc_type) throw new ApiError(serverMessage(payload), payload.exc_type)
	return payload.message
}

export function printUrl(doctype, name, format = "Standard", pdf = false, letterhead = "") {
	const params = new URLSearchParams({ doctype, name, format, no_letterhead: letterhead ? "0" : "1" })
	if (letterhead) params.set("letterhead", letterhead)
	if (pdf) return `/api/method/frappe.utils.print_format.download_pdf?${params}`
	return `/printview?${params}&trigger_print=1`
}
