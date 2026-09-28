<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { DOCTYPES, VAT_LABELS, docStatusLabel, formatCurrency, formatDate, formatNumber, isOverdue, session } from "@/utils"
import ActivityPanel from "@/components/ActivityPanel.vue"
import ConnectionsPanel from "@/components/ConnectionsPanel.vue"
import EmailDialog from "@/components/EmailDialog.vue"
import Modal from "@/components/Modal.vue"
import PaymentDialog from "@/components/PaymentDialog.vue"
import PrintDialog from "@/components/PrintDialog.vue"
import UpdateItemsDialog from "@/components/UpdateItemsDialog.vue"
import PageHeader from "@/components/PageHeader.vue"
import StatusPill from "@/components/StatusPill.vue"

const props = defineProps({ kind: { type: String, required: true }, docname: { type: String, required: true } })
const config = computed(() => DOCTYPES[props.kind])
const ctx = computed(() => session.context)
const doc = ref(null)
const error = ref("")
const busy = ref(false)
const emailOpen = ref(false)
const printOpen = ref(false)
const updateOpen = ref(false)
const confirmOpen = ref(false)
const paymentOpen = ref(false)
const activity = ref(null)
const connections = ref(null)

const status = computed(() => (!doc.value ? "" : props.kind === "invoices" && isOverdue(doc.value) ? "Overdue" : docStatusLabel(doc.value)))
const isDraft = computed(() => doc.value?.docstatus === 0)
// POs raised outside the workspace (no catalog/BOQ control) are read-only here and handled in Desk
// invoices have no controlled flag: everything about them is handled here
const isControlled = computed(() => props.kind === "invoices" || Boolean(doc.value?.controlled_procurement))
const deskUrl = computed(() => `/app/${config.value.doctype.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(props.docname)}`)
const canSubmit = computed(() => isDraft.value && (props.kind === "transfers" ? ctx.value.can_transfer : ctx.value.can_purchase))
const canReceive = computed(() => props.kind === "orders" && doc.value?.docstatus === 1 && (doc.value.per_received || 0) < 100 && !["Closed", "On Hold"].includes(doc.value.status))
const canUpdateItems = computed(() => props.kind === "orders" && doc.value?.docstatus === 1 && ctx.value.can_purchase && !["Closed", "Completed", "Delivered"].includes(doc.value.status))
const canInvoice = computed(() => ["orders", "receipts"].includes(props.kind) && doc.value?.docstatus === 1 && ctx.value.can_purchase
	&& (doc.value.per_billed || 0) < 100 && !doc.value.is_return && !["Closed", "On Hold"].includes(doc.value.status))
const canPay = computed(() => props.kind === "invoices" && doc.value?.docstatus === 1 && Number(doc.value.outstanding_amount) > 0 && ctx.value.can_purchase)
const canEmail = computed(() => props.kind !== "transfers" && doc.value?.docstatus !== 2)
const partyName = computed(() => doc.value?.supplier_name || doc.value?.supplier || "")

const summary = computed(() => {
	const d = doc.value
	if (!d) return []
	const cards = []
	if (d.supplier) cards.push({ label: "Supplier", value: partyName.value })
	cards.push({ label: "Project", value: d.project || "—", hint: [d.bill_no, d.boq_item].filter(Boolean).join(" · ") })
	if (props.kind === "orders") {
		cards.push({ label: "Value", value: formatCurrency(d.grand_total, d.currency), strong: true, hint: d.schedule_date ? `Required by ${formatDate(d.schedule_date)}` : "" })
		cards.push({ label: "Received", value: `${Math.round(d.per_received || 0)}%`, strong: true, hint: `Billed ${Math.round(d.per_billed || 0)}%` })
	} else if (props.kind === "invoices") {
		cards.push({ label: "Invoice value", value: formatCurrency(d.grand_total, d.currency), strong: true, hint: d.custom_supplier_invoice_no ? `Supplier inv ${d.custom_supplier_invoice_no}` : "" })
		cards.push({ label: "Outstanding", value: formatCurrency(d.outstanding_amount, d.currency), strong: true, hint: d.due_date ? `Due ${formatDate(d.due_date)}` : "" })
	} else if (props.kind === "receipts") {
		cards.push({ label: "Received on", value: formatDate(d.posting_date), hint: d.custom_purchase_order ? `Against ${d.custom_purchase_order}` : "" })
		cards.push({ label: "Value received", value: formatCurrency(d.grand_total, d.currency), strong: true })
	} else {
		cards.push({ label: "Posting date", value: formatDate(d.posting_date) })
		cards.push({ label: "Total value", value: formatCurrency(d.total_outgoing_value || d.value_difference), strong: true })
	}
	return cards
})

// item descriptions are Text Editor HTML; show them as plain text
function plainText(html) {
	const div = document.createElement("div")
	div.innerHTML = html || ""
	return (div.textContent || "").replace(/\s+/g, " ").trim()
}

function time(value) {
	return value ? String(value).slice(0, 5) : ""
}

// key/value facts shown in the Details card; empty values are dropped
const details = computed(() => {
	const d = doc.value
	if (!d) return []
	const common = [["Company", d.company], ["Currency", d.currency && d.currency !== ctx.value.currency ? d.currency : ""], ["Created by", d.owner_name], ["Created on", formatDate(d.creation)]]
	let rows = []
	if (props.kind === "orders") {
		rows = [
			["Order date", formatDate(d.transaction_date)], ["Required by", formatDate(d.schedule_date)],
			["Deliver to", d.set_warehouse], ["Supplier quotation", d.items?.find((row) => row.supplier_quotation)?.supplier_quotation],
			["Material request", [...new Set((d.items || []).map((row) => row.material_request).filter(Boolean))].join(", ")],
			["Payment terms", d.payment_terms_template], ["Tax template", d.taxes_and_charges], ["Bill No / BOQ", [d.bill_no, d.boq_item].filter(Boolean).join(" · ")],
			["Supplier address", d.address_display ? d.address_display.replace(/<br\s*\/?>/g, ", ").replace(/,\s*$/, "") : ""],
		]
	} else if (props.kind === "invoices") {
		rows = [
			["Supplier invoice no", d.custom_supplier_invoice_no], ["Supplier invoice date", formatDate(d.bill_date)],
			["Posting date", formatDate(d.posting_date)], ["Due date", formatDate(d.due_date)],
			["Against", [...new Set((d.items || []).flatMap((row) => [row.purchase_order, row.purchase_receipt]).filter(Boolean))].join(", ")],
			["Payable account", d.credit_to], ["Tax template", d.taxes_and_charges], ["Bill No / BOQ", [d.bill_no, d.boq_item].filter(Boolean).join(" · ")],
			["Remarks", d.remarks && d.remarks !== "No Remarks" ? d.remarks : ""],
		]
	} else if (props.kind === "receipts") {
		rows = [
			["Posting", `${formatDate(d.posting_date)} ${time(d.posting_time)}`.trim()], ["Warehouse", d.set_warehouse],
			["Supplier delivery note", d.supplier_delivery_note], ["Against PO", [...new Set((d.items || []).map((row) => row.purchase_order).filter(Boolean))].join(", ")],
			["Bill No / BOQ", [d.bill_no, d.boq_item].filter(Boolean).join(" · ")], ["Transporter", d.transporter_name], ["Vehicle", d.lr_no],
		]
	} else {
		rows = [
			["Posting", `${formatDate(d.posting_date)} ${time(d.posting_time)}`.trim()], ["Entry type", d.stock_entry_type],
			["From warehouse", d.from_warehouse], ["To warehouse", d.to_warehouse],
			["Bill No / BOQ", [d.bill_no, d.boq_item].filter(Boolean).join(" · ")], ["Remarks", d.remarks],
		]
	}
	return [...rows, ...common].filter(([, value]) => value)
})

const hasTotals = computed(() => props.kind !== "transfers" && doc.value)

function onPaid() {
	paymentOpen.value = false
	load()
	activity.value?.load()
	connections.value?.load()
}

async function load() {
	try {
		doc.value = await call("get_controlled_document", { doctype: config.value.doctype, name: props.docname })
	} catch (requestError) {
		error.value = requestError.message
	}
}

async function submit() {
	confirmOpen.value = false
	busy.value = true
	try {
		await call("submit_document", { doctype: config.value.doctype, name: props.docname })
		toast(`${props.docname} submitted`)
		await load()
		activity.value?.load()
		connections.value?.load()
	} catch (requestError) {
		toastError(requestError)
	} finally {
		busy.value = false
	}
}

function onEmailSent() {
	emailOpen.value = false
	activity.value?.load()
}

onMounted(load)
</script>

<template>
	<div v-if="error" class="cp-card cp-error-card">
		<strong>Could not open {{ docname }}</strong>
		<p>{{ error }}</p>
		<RouterLink :to="config.path" class="cp-btn">Back to {{ config.title.toLowerCase() }}</RouterLink>
	</div>
	<template v-else-if="doc">
		<PageHeader :title="doc.name" :subtitle="[partyName, doc.project].filter(Boolean).join(' · ')" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: config.title, to: config.path }, { label: doc.name }]">
			<template #actions>
				<StatusPill v-if="doc.custom_is_provisional_po" status="Open PO" title="Provisional / Open PO — receipts may exceed the ordered qty" />
				<StatusPill :status="status" />
				<button class="cp-btn" @click="printOpen = true">
					<svg viewBox="0 0 24 24"><path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></svg>Print / PDF
				</button>
				<button v-if="canEmail" class="cp-btn" @click="emailOpen = true">
					<svg viewBox="0 0 24 24"><path d="M4 6h16v12H4zM4 7l8 6 8-6" /></svg>Email
				</button>
				<RouterLink v-if="canReceive" :to="{ path: '/receipts/new', query: { po: doc.name } }" class="cp-btn brand">+ Receive goods</RouterLink>
				<RouterLink v-if="canInvoice" :to="{ path: '/invoices/new', query: kind === 'orders' ? { po: doc.name } : { pr: doc.name } }" class="cp-btn">+ Create invoice</RouterLink>
				<button v-if="canUpdateItems" class="cp-btn" @click="updateOpen = true">Update items</button>
				<button v-if="canPay" class="cp-btn brand" @click="paymentOpen = true">Record payment</button>
				<button v-if="canSubmit" class="cp-btn brand" :disabled="busy" @click="confirmOpen = true">{{ busy ? "Submitting…" : "Submit" }}</button>
				<a v-if="!isControlled" class="cp-btn" :href="deskUrl" target="_blank">Open in Desk ↗</a>
			</template>
		</PageHeader>

		<div v-if="!isControlled" class="cp-banner">Raised outside Controlled Procurement — view, print, email, comment, submit and receive here; edit the draft in Desk.</div>
		<div v-else-if="isDraft" class="cp-banner">Draft — not posted yet. Submit it to {{ kind === "orders" ? "send the order to the supplier" : kind === "invoices" ? "book the payable" : "post it to stock" }}.</div>

		<div class="cp-stats">
			<div v-for="card in summary" :key="card.label" class="cp-stat static">
				<small>{{ card.label }}</small>
				<strong :class="{ plain: !card.strong }">{{ card.value }}</strong>
				<span v-if="card.hint">{{ card.hint }}</span>
			</div>
		</div>

		<section class="cp-card">
			<header class="cp-card-head"><h3>Details</h3></header>
			<dl class="cp-details">
				<div v-for="[label, value] in details" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div>
			</dl>
		</section>

		<section class="cp-card">
			<header class="cp-card-head"><h3>{{ kind === "receipts" ? "Items received" : "Items" }}</h3><span v-if="kind === 'receipts' && doc.set_warehouse" class="cp-muted">Into {{ doc.set_warehouse }}</span></header>
			<table class="cp-table">
				<thead>
					<tr>
						<th>Description</th>
						<th>Allocation</th>
						<th v-if="kind === 'transfers'">From → To</th>
						<th v-if="kind !== 'transfers'">Warehouse</th>
						<th class="num">Qty</th>
						<th>UOM</th>
						<th class="num">Rate</th>
						<th v-if="kind !== 'transfers'">VAT</th>
						<th class="num">Amount</th>
						<th v-if="kind === 'orders'" class="num">Received</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in doc.items" :key="row.name">
						<td>
							<strong>{{ row.item_name || row.item_code }}</strong>
							<small>{{ row.item_code }}<template v-if="row.controlled_item_type"> · {{ row.controlled_item_type }}</template></small>
							<small v-if="plainText(row.description) && plainText(row.description) !== row.item_name" class="cp-note">{{ plainText(row.description) }}</small>
						</td>
						<td>{{ row.project || "—" }}<small>{{ [row.bill_no, row.boq_item].filter(Boolean).join(" · ") }}</small></td>
						<td v-if="kind === 'transfers'">{{ row.s_warehouse }} → {{ row.t_warehouse }}</td>
						<td v-if="kind !== 'transfers'">{{ row.warehouse || "—" }}</td>
						<td class="num">{{ formatNumber(row.qty) }}</td>
						<td>{{ row.uom }}</td>
						<td class="num">{{ formatCurrency(row.rate || row.basic_rate, doc.currency) }}</td>
						<td v-if="kind !== 'transfers'"><span class="cp-pill" :class="row.vat === 'standard' ? 'neutral' : 'info'">{{ doc.taxes_and_charges ? VAT_LABELS[row.vat] : "No tax" }}</span></td>
						<td class="num"><strong>{{ formatCurrency(row.amount, doc.currency) }}</strong></td>
						<td v-if="kind === 'orders'" class="num">{{ formatNumber(row.received_qty) }} / {{ formatNumber(row.qty) }}</td>
					</tr>
				</tbody>
				<tfoot v-if="kind !== 'transfers'">
					<tr>
						<td :colspan="7" class="num">Net total</td>
						<td class="num"><strong>{{ formatCurrency(doc.net_total || doc.total, doc.currency) }}</strong></td>
						<td v-if="kind === 'orders'" />
					</tr>
				</tfoot>
			</table>
		</section>

		<div v-if="hasTotals" class="cp-two-col">
			<section class="cp-card">
				<header class="cp-card-head"><h3>Taxes &amp; charges</h3></header>
				<table class="cp-table compact">
					<thead><tr><th>Description</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead>
					<tbody>
						<tr v-for="tax in doc.taxes" :key="tax.name"><td>{{ tax.description || tax.account_head }}</td><td class="num">{{ tax.rate ? `${tax.rate}%` : "—" }}</td><td class="num">{{ formatCurrency(tax.tax_amount, doc.currency) }}</td></tr>
						<tr v-if="!doc.taxes?.length"><td colspan="3" class="cp-empty-row">No taxes applied.</td></tr>
					</tbody>
				</table>
			</section>
			<section class="cp-card">
				<header class="cp-card-head"><h3>Totals</h3></header>
				<dl class="cp-totals">
					<div><dt>Net total</dt><dd>{{ formatCurrency(doc.net_total || doc.total, doc.currency) }}</dd></div>
					<div v-if="doc.discount_amount"><dt>Discount</dt><dd>− {{ formatCurrency(doc.discount_amount, doc.currency) }}</dd></div>
					<div><dt>Taxes &amp; charges</dt><dd>{{ formatCurrency(doc.total_taxes_and_charges, doc.currency) }}</dd></div>
					<div class="grand"><dt>Grand total</dt><dd>{{ formatCurrency(doc.grand_total, doc.currency) }}</dd></div>
					<div v-if="doc.in_words" class="words"><dd>{{ doc.in_words }}</dd></div>
				</dl>
			</section>
		</div>

		<ConnectionsPanel ref="connections" :doctype="config.doctype" :docname="doc.name" />

		<div v-if="doc.attachments?.length">
			<section v-if="doc.attachments?.length" class="cp-card">
				<header class="cp-card-head"><h3>Attachments</h3></header>
				<ul class="cp-files">
					<li v-for="file in doc.attachments" :key="file.name"><a :href="file.file_url" target="_blank" class="cp-link">📎 {{ file.file_name }}</a><small>{{ formatDate(file.creation) }}</small></li>
				</ul>
			</section>
		</div>

		<section v-if="doc.terms" class="cp-card">
			<header class="cp-card-head"><h3>Terms &amp; conditions</h3></header>
			<!-- eslint-disable-next-line vue/no-v-html -- terms are Text Editor HTML stored on the document -->
			<div class="cp-rich cp-terms" v-html="doc.terms" />
		</section>

		<ActivityPanel ref="activity" :doctype="config.doctype" :docname="doc.name" />
		<Modal v-if="confirmOpen" :title="`Submit ${doc.name}?`" @close="confirmOpen = false">
			<p style="margin: 0">
				Submitting posts this {{ config.single.toLowerCase() }} to the {{ kind === "orders" ? "supplier and books" : "stock ledger" }}.
				It can't be edited afterwards, only cancelled{{ kind === "orders" ? " or changed with Update items" : "" }}.
			</p>
			<div class="cp-confirm-summary">
				<span>{{ partyName || doc.project || doc.company }}</span>
				<strong>{{ formatCurrency(doc.grand_total || doc.total_outgoing_value, doc.currency) }}</strong>
			</div>
			<template #footer>
				<button type="button" class="cp-btn" @click="confirmOpen = false">Cancel</button>
				<button type="button" class="cp-btn primary" :disabled="busy" @click="submit">Submit</button>
			</template>
		</Modal>
		<UpdateItemsDialog v-if="updateOpen" :doc="doc" @close="updateOpen = false" @updated="updateOpen = false; load(); activity?.load()" />
		<PaymentDialog v-if="paymentOpen" :invoice="doc.name" @close="paymentOpen = false" @paid="onPaid" />
		<PrintDialog v-if="printOpen" :doctype="config.doctype" :docname="doc.name" @close="printOpen = false" />
		<EmailDialog v-if="emailOpen" :doctype="config.doctype" :docname="doc.name" @close="emailOpen = false" @sent="onEmailSent" />
	</template>
	<div v-else class="cp-muted">Loading {{ docname }}…</div>
</template>
