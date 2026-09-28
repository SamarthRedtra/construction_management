import { reactive } from "vue"

// `version` bumps on company switch so open views reload their data
export const session = reactive({ context: null, version: 0 })

// link filters that keep pickers inside the active company
export function companyFilters(extra = {}) {
	const company = session.context?.default_company
	return company ? { company, ...extra } : { ...extra }
}

export function formatCurrency(value, currency) {
	const code = currency || session.context?.currency || "AED"
	const amount = Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 })
	return `${code} ${amount}`
}

export function formatNumber(value) {
	return Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 3 })
}

export function formatDate(value) {
	if (!value) return ""
	const date = new Date(`${String(value).slice(0, 10)}T00:00:00`)
	return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
}

export function timeAgo(value) {
	if (!value) return ""
	const seconds = Math.round((Date.now() - new Date(String(value).replace(" ", "T")).getTime()) / 1000)
	if (seconds < 60) return "just now"
	const units = [["year", 31536000], ["month", 2592000], ["day", 86400], ["hour", 3600], ["minute", 60]]
	for (const [unit, size] of units) {
		const count = Math.floor(seconds / size)
		if (count >= 1) return `${count} ${unit}${count > 1 ? "s" : ""} ago`
	}
	return ""
}

export function today() {
	const now = new Date()
	return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

export function debounce(fn, wait = 300) {
	let timer
	return (...args) => {
		clearTimeout(timer)
		timer = setTimeout(() => fn(...args), wait)
	}
}

export function docStatusLabel(doc) {
	if (doc.docstatus === 0) return "Draft"
	if (doc.docstatus === 2) return "Cancelled"
	return doc.status || "Submitted"
}

// UI names for doctypes that are called something else on screen (data and API keep the doctype name)
export const DOCTYPE_LABELS = { "Purchase Receipt": "Receive Note" }

export function doctypeLabel(doctype) {
	return DOCTYPE_LABELS[doctype] || doctype
}

export const VAT_LABELS = { standard: "5%", zero: "Zero", exempt: "Exempt" }

export function isOverdue(row) {
	return row.docstatus === 1 && Number(row.outstanding_amount) > 0 && row.due_date && String(row.due_date).slice(0, 10) < today()
}

export const DOCTYPES = {
	orders: { doctype: "Purchase Order", title: "Purchase Orders", single: "Purchase Order", path: "/purchase-orders" },
	receipts: { doctype: "Purchase Receipt", title: "Receive Notes", single: "Receive Note", path: "/receipts" },
	invoices: { doctype: "Purchase Invoice", title: "Purchase Invoices", single: "Purchase Invoice", path: "/invoices" },
	transfers: { doctype: "Stock Entry", title: "Material Transfers", single: "Material Transfer", path: "/transfers" },
}

export function kindFor(doctype) {
	return Object.keys(DOCTYPES).find((kind) => DOCTYPES[kind].doctype === doctype)
}
