<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, previewUrl } from "@/api"
import { DOCTYPES, debounce, docStatusLabel, formatCurrency, formatDate, formatNumber, isOverdue } from "@/utils"
import { toast, toastError } from "@/toast"
import PageHeader from "@/components/PageHeader.vue"
import PaginationBar from "@/components/PaginationBar.vue"
import PrintDialog from "@/components/PrintDialog.vue"
import StatusPill from "@/components/StatusPill.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import { companyFilters } from "@/utils"

const PAGE_SIZE = 25

const props = defineProps({ kind: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const createdOrder = computed(() => props.kind === "orders" ? String(route.query.created || "") : "")
const config = computed(() => DOCTYPES[props.kind])
const rows = ref([])
const total = ref(0)
const page = ref(Math.max(1, Number(route.query.page) || 1))
const search = ref("")
const docstatus = ref("")
const sortBy = ref("modified")
const sortOrder = ref("desc")
const loading = ref(false)
const printing = ref("")
const previewName = ref("")
const previewDoc = ref(null)
const previewLoading = ref(false)
const previewBusy = ref(false)
const showPrintLayout = ref(false)
const filters = reactive({ supplier: "", project: "", lpo_type: "", purchase_order: "", warehouse: "", from_warehouse: "", to_warehouse: "", item_code: "", date_from: "", date_to: "" })
function clearFilters() { for (const key of Object.keys(filters)) filters[key] = "" }

function syncPageQuery() {
	const query = { ...route.query }
	if (page.value > 1) query.page = String(page.value)
	else delete query.page
	router.replace({ query })
}

function resetToFirstPage() {
	if (page.value !== 1) page.value = 1
	else load()
}

const previewFrameUrl = computed(() => {
	if (!previewDoc.value || !showPrintLayout.value) return ""
	return previewUrl(config.value.doctype, previewDoc.value.name)
})

const previewItems = computed(() => (previewDoc.value?.items || []).slice(0, 8))
const previewItemsMore = computed(() => Math.max((previewDoc.value?.items || []).length - 8, 0))

function lineAmount(row) {
	if (props.kind === "transfers") return Number(row.amount || row.basic_amount || (row.qty || 0) * (row.basic_rate || row.valuation_rate || 0))
	return Number(row.amount || (row.qty || 0) * (row.rate || 0))
}

function lineRate(row) {
	if (props.kind === "transfers") return row.basic_rate || row.valuation_rate || 0
	return row.rate || 0
}

async function load() {
	loading.value = true
	try {
		const result = await call("get_controlled_documents", {
			doctype: config.value.doctype,
			search: search.value,
			docstatus: docstatus.value,
			sort_by: sortBy.value,
			sort_order: sortOrder.value,
			start: (page.value - 1) * PAGE_SIZE,
			page_length: PAGE_SIZE,
			...filters,
		})
		rows.value = result.rows
		total.value = result.total_count
		const maxPage = Math.max(1, Math.ceil((result.total_count || 0) / PAGE_SIZE) || 1)
		if (page.value > maxPage) {
			page.value = maxPage
			return
		}
		syncPageQuery()
		if (previewName.value && !rows.value.some((row) => row.name === previewName.value)) {
			closePreview()
		}
	} finally {
		loading.value = false
	}
}

function dateOf(row) {
	return row.transaction_date || row.posting_date
}

const filterTabs = computed(() => [
	{ value: "", label: "All" },
	{ value: "0", label: "Draft" },
	...(props.kind === "invoices" ? [{ value: "unpaid", label: "Unpaid" }, { value: "overdue", label: "Overdue" }] : [{ value: "1", label: "Submitted" }]),
	...(["orders", "receipts", "transfers"].includes(props.kind) ? [{ value: "2", label: "Cancelled" }] : []),
])
const sortFields = computed(() => [
	{ value: "modified", label: "Last updated" }, { value: "name", label: "Document number" },
	...(["orders", "receipts", "invoices"].includes(props.kind) ? [{ value: "supplier", label: "Supplier" }] : []),
	{ value: "project", label: "Project" }, { value: "date", label: "Date" },
	{ value: "status", label: "Status" }, { value: "value", label: "Value" },
	...(props.kind === "orders" ? [{ value: "received", label: "Received %" }] : []),
])

const hasAdvancedFilters = computed(() => props.kind !== "invoices")

function rowStatus(row) {
	if (props.kind === "invoices" && isOverdue(row)) return "Overdue"
	return docStatusLabel(row)
}

async function selectPreview(name) {
	previewName.value = name
	previewLoading.value = true
	previewDoc.value = null
	showPrintLayout.value = false
	await nextTick()
	document.querySelector(`tr[data-doc="${CSS.escape(name)}"]`)?.scrollIntoView({ block: "nearest" })
	try {
		previewDoc.value = await call("get_controlled_document", { doctype: config.value.doctype, name })
		const query = { ...route.query, preview: name }
		router.replace({ query })
	} catch (error) {
		toastError(error)
		closePreview()
	} finally {
		previewLoading.value = false
	}
}

function closePreview() {
	previewName.value = ""
	previewDoc.value = null
	showPrintLayout.value = false
	const query = { ...route.query }
	delete query.preview
	router.replace({ query })
}

function openDetail(name) {
	router.push(`${config.value.path}/${encodeURIComponent(name)}`)
}

async function previewAction(action) {
	if (!previewDoc.value) return
	const methods = {
		orders: { cancel: "cancel_purchase_order", amend: "amend_purchase_order", delete: "delete_purchase_order" },
		receipts: { cancel: "cancel_purchase_receipt", amend: "amend_purchase_receipt", delete: "delete_purchase_receipt" },
		invoices: { cancel: "cancel_purchase_invoice", amend: "amend_purchase_invoice" },
		transfers: { cancel: "cancel_material_transfer", amend: "amend_material_transfer" },
	}
	const method = methods[props.kind]?.[action]
	if (!method) return
	if (action === "cancel" && !window.confirm(`Cancel this ${config.value.single}?`)) return
	if (action === "delete" && !window.confirm(`Delete this ${config.value.single}?`)) return
	previewBusy.value = true
	try {
		const result = await call(method, { name: previewDoc.value.name })
		const done = { cancel: "cancelled", amend: `amended → ${result.name}`, delete: "deleted" }[action] || action
		toast(`${previewDoc.value.name} ${done}`)
		if (action === "delete") closePreview()
		else if (action === "amend" && result.name) await selectPreview(result.name)
		else await selectPreview(previewDoc.value.name)
		await load()
	} catch (error) {
		toastError(error)
	} finally {
		previewBusy.value = false
	}
}

const canPreviewCancel = computed(() => previewDoc.value?.docstatus === 1 && previewDoc.value?.can_cancel)
const canPreviewAmend = computed(() => previewDoc.value?.docstatus === 2 && previewDoc.value?.can_amend)
const canPreviewDelete = computed(() => ["orders", "receipts"].includes(props.kind) && previewDoc.value?.can_delete)

watch(search, debounce(() => resetToFirstPage(), 300))
watch(docstatus, () => resetToFirstPage())
watch([sortBy, sortOrder], () => resetToFirstPage())
watch(filters, debounce(() => resetToFirstPage(), 250))
watch(page, () => load())
onMounted(async () => {
	await load()
	const initial = String(route.query.preview || "")
	if (initial) await selectPreview(initial)
})
</script>

<template>
	<PageHeader :title="config.title" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: config.title }]">
		<template #actions>
			<RouterLink :to="`${config.path}/new`" class="cp-btn primary">New {{ config.single.toLowerCase() }}</RouterLink>
		</template>
	</PageHeader>
	<p v-if="createdOrder" class="cp-hint" role="status">Purchase Order {{ createdOrder }} was created as a draft. Review it below before submitting.</p>

	<section class="cp-filter-panel">
		<div class="cp-filter-toolbar">
			<input v-model="search" class="cp-input cp-search" :placeholder="kind === 'orders' ? 'Search by ID, supplier or project' : kind === 'invoices' ? 'Search by ID, supplier, supplier invoice no or project' : kind === 'receipts' ? 'Search by ID, supplier, delivery note no or project' : `Search ${config.title.toLowerCase()} by ID, supplier or project`" />
			<div class="cp-sort-control" title="Sort documents">
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h14M3 12h10M3 18h6M18 10l3 3-3 3M21 13V5" /></svg>
				<select v-model="sortBy" class="cp-input" aria-label="Sort by"><option v-for="field in sortFields" :key="field.value" :value="field.value">{{ field.label }}</option></select>
				<button type="button" class="cp-icon-button sm" :title="sortOrder === 'asc' ? 'Ascending; click for descending' : 'Descending; click for ascending'" :aria-label="sortOrder === 'asc' ? 'Sort ascending' : 'Sort descending'" @click="sortOrder = sortOrder === 'asc' ? 'desc' : 'asc'"><svg viewBox="0 0 24 24"><path :d="sortOrder === 'asc' ? 'M12 20V4m-5 5 5-5 5 5' : 'M12 4v16m-5-5 5 5 5-5'" /></svg></button>
			</div>
			<div class="cp-segmented">
				<button v-for="tab in filterTabs" :key="tab.value" :class="{ active: docstatus === tab.value }" @click="docstatus = tab.value">{{ tab.label }}</button>
			</div>
		</div>
		<div v-if="hasAdvancedFilters" class="cp-filter-advanced">
			<div class="cp-grid-3">
				<LinkSelect v-if="kind === 'orders' || kind === 'receipts'" v-model="filters.supplier" doctype="Supplier" label="Supplier" />
				<LinkSelect v-if="kind === 'orders' || kind === 'receipts'" v-model="filters.project" doctype="Project" label="Project" :filters="companyFilters()" />
				<label v-if="kind === 'orders'" class="cp-field"><span>LPO type</span><select v-model="filters.lpo_type" class="cp-input"><option value="">All types</option><option>Standard</option><option>Open</option><option>Manual</option></select></label>
				<label v-if="kind === 'receipts'" class="cp-field"><span>Purchase Order</span><input v-model="filters.purchase_order" class="cp-input" placeholder="PO number" /></label>
				<LinkSelect v-if="kind === 'receipts'" v-model="filters.warehouse" doctype="Warehouse" label="Warehouse" :filters="companyFilters({ is_group: 0 })" />
				<LinkSelect v-if="kind === 'transfers'" v-model="filters.from_warehouse" doctype="Warehouse" label="From warehouse" :filters="companyFilters({ is_group: 0 })" />
				<LinkSelect v-if="kind === 'transfers'" v-model="filters.to_warehouse" doctype="Warehouse" label="To warehouse" :filters="companyFilters({ is_group: 0 })" />
				<LinkSelect v-if="kind === 'transfers'" v-model="filters.item_code" doctype="Item" label="Item" />
				<label class="cp-field"><span>From date</span><input v-model="filters.date_from" type="date" class="cp-input" /></label>
				<label class="cp-field"><span>To date</span><input v-model="filters.date_to" type="date" class="cp-input" /></label>
			</div>
			<div class="cp-filter-foot">
				<button type="button" class="cp-link sm" @click="clearFilters">Clear filters</button>
			</div>
		</div>
	</section>

	<div class="cp-list-split" :class="{ 'has-preview': previewName }">
		<section class="cp-card cp-list-pane">
			<table class="cp-table cp-list-table">
				<thead>
					<tr>
						<th>{{ config.single }}</th>
						<th>Project</th>
						<th v-if="kind === 'receipts'">Delivery note no.</th>
						<th>Date</th>
						<th v-if="kind === 'orders'">Received</th>
						<th>Status</th>
						<th class="num">Value</th>
						<th v-if="kind === 'invoices'" class="num">Outstanding</th>
						<th style="width: 48px" />
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="row in rows"
						:key="row.name"
						class="clickable"
						:data-doc="row.name"
						:class="{ 'cp-new-order-row': row.name === createdOrder, 'cp-row-selected': row.name === previewName }"
						@click="selectPreview(row.name)"
						@dblclick="openDetail(row.name)"
					>
						<td>
							<div class="cp-doc-cell">
								<div class="cp-doc-title">
									<strong class="cp-doc-name">{{ row.name }}</strong>
									<span v-if="row.controlled_procurement" class="cp-pill info sm" title="Controlled procurement document">Controlled</span>
									<span v-if="row.has_catalog_items" class="cp-pill info sm" title="Contains controlled catalog item lines">Catalog</span>
								</div>
								<small v-if="row.supplier" class="cp-doc-sub" :title="row.supplier_name || row.supplier">{{ row.supplier_name || row.supplier }}</small>
								<small v-if="kind === 'orders'" class="cp-doc-meta">{{ row.custom_lpo_type || (row.custom_is_provisional_po ? 'Open' : 'Standard') }} LPO<template v-if="row.custom_lpo_approval_status"> · {{ row.custom_lpo_approval_status }}</template></small>
								<small v-if="row.custom_supplier_invoice_no" class="cp-doc-meta">Supplier inv {{ row.custom_supplier_invoice_no }}</small>
							</div>
						</td>
						<td>{{ row.project || "—" }}<small v-if="row.bill_no">{{ row.bill_no }}</small></td>
						<td v-if="kind === 'receipts'">{{ row.supplier_delivery_note || "—" }}</td>
						<td>{{ formatDate(dateOf(row)) }}<small v-if="row.schedule_date || row.due_date" :class="{ 'cp-overdue': kind === 'invoices' && isOverdue(row) }">Due {{ formatDate(row.schedule_date || row.due_date) }}</small></td>
						<td v-if="kind === 'orders'">
							<div class="cp-received">
								<div class="cp-progress"><i :style="{ width: `${Math.min(row.per_received || 0, 100)}%` }" /></div>
								<small>{{ Math.round(row.per_received || 0) }}%</small>
							</div>
						</td>
						<td><StatusPill :status="rowStatus(row)" /></td>
						<td class="num">{{ formatCurrency(kind === 'transfers' ? row.total_outgoing_value : row.grand_total) }}</td>
						<td v-if="kind === 'invoices'" class="num"><strong v-if="row.docstatus === 1">{{ formatCurrency(row.outstanding_amount) }}</strong><span v-else class="cp-muted">—</span></td>
						<td class="num"><button class="cp-icon-button sm" title="Print / PDF" aria-label="Print" @click.stop="printing = row.name"><svg viewBox="0 0 24 24"><path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></svg></button></td>
					</tr>
					<tr v-if="!loading && !rows.length"><td :colspan="kind === 'orders' || kind === 'invoices' || kind === 'receipts' ? 7 : 6" class="cp-empty-row">No {{ config.title.toLowerCase() }} found.</td></tr>
				</tbody>
			</table>
			<PaginationBar v-model:page="page" :page-size="PAGE_SIZE" :total="total" :loading="loading" />
		</section>

		<aside v-if="previewName" class="cp-card cp-preview-pane">
			<header class="cp-preview-head">
				<div class="cp-preview-title">
					<strong>{{ previewName }}</strong>
					<StatusPill v-if="previewDoc" :status="rowStatus(previewDoc)" />
				</div>
				<button type="button" class="cp-icon-button sm" title="Close preview" aria-label="Close preview" @click="closePreview">×</button>
			</header>
			<div v-if="previewLoading" class="cp-preview-empty">Loading preview…</div>
			<template v-else-if="previewDoc">
				<div class="cp-preview-actions">
					<button type="button" class="cp-btn sm brand" @click="openDetail(previewDoc.name)">Open</button>
					<button type="button" class="cp-btn sm" @click="printing = previewDoc.name">Print / PDF</button>
					<button v-if="canPreviewCancel" type="button" class="cp-btn sm" :disabled="previewBusy" @click="previewAction('cancel')">Cancel</button>
					<button v-if="canPreviewAmend" type="button" class="cp-btn sm" :disabled="previewBusy" @click="previewAction('amend')">Amend</button>
					<button v-if="canPreviewDelete" type="button" class="cp-btn sm" :disabled="previewBusy" @click="previewAction('delete')">Delete</button>
					<button type="button" class="cp-btn sm" :class="{ primary: showPrintLayout }" @click="showPrintLayout = !showPrintLayout">{{ showPrintLayout ? "Summary" : "Print layout" }}</button>
				</div>

				<template v-if="!showPrintLayout">
					<div class="cp-preview-summary">
						<div v-if="kind !== 'transfers'"><small>Supplier</small><strong :title="previewDoc.supplier_name || previewDoc.supplier || ''">{{ previewDoc.supplier_name || previewDoc.supplier || "—" }}</strong></div>
						<div v-if="kind === 'transfers'"><small>From warehouse</small><strong>{{ previewDoc.from_warehouse || "—" }}</strong></div>
						<div v-if="kind === 'transfers'"><small>To warehouse</small><strong>{{ previewDoc.to_warehouse || "—" }}</strong></div>
						<div><small>Project</small><strong>{{ previewDoc.project || "—" }}</strong></div>
						<div><small>Date</small><strong>{{ formatDate(dateOf(previewDoc)) }}</strong></div>
						<div><small>Value</small><strong>{{ formatCurrency(kind === 'transfers' ? previewDoc.total_outgoing_value : previewDoc.grand_total) }}</strong></div>
						<div v-if="kind === 'receipts'"><small>Delivery note</small><strong>{{ previewDoc.supplier_delivery_note || "—" }}</strong></div>
						<div v-if="kind === 'invoices'"><small>Outstanding</small><strong>{{ previewDoc.docstatus === 1 ? formatCurrency(previewDoc.outstanding_amount) : "—" }}</strong></div>
					</div>

					<div class="cp-preview-items">
						<div class="cp-preview-items-head">
							<span>Items</span>
							<small>{{ (previewDoc.items || []).length }} line{{ (previewDoc.items || []).length === 1 ? "" : "s" }}</small>
						</div>
						<table v-if="previewItems.length" class="cp-table compact cp-preview-item-table">
							<thead>
								<tr>
									<th>Item</th>
									<th class="num">Qty</th>
									<th class="num">Rate</th>
									<th class="num">Amount</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="(row, idx) in previewItems" :key="row.name || idx">
									<td>
										<strong>{{ row.item_name || row.item_code }}</strong>
										<small v-if="row.item_code && row.item_name">{{ row.item_code }}</small>
									</td>
									<td class="num">{{ formatNumber(row.qty) }} <small v-if="row.uom || row.stock_uom">{{ row.uom || row.stock_uom }}</small></td>
									<td class="num">{{ formatCurrency(lineRate(row)) }}</td>
									<td class="num">{{ formatCurrency(lineAmount(row)) }}</td>
								</tr>
							</tbody>
						</table>
						<p v-else class="cp-preview-empty">No item lines on this document.</p>
						<p v-if="previewItemsMore" class="cp-hint cp-preview-more">+ {{ previewItemsMore }} more · Open for full detail</p>
					</div>
				</template>
				<iframe v-else class="cp-preview-frame" :src="previewFrameUrl" title="Document print layout" />
			</template>
		</aside>
	</div>
	<PrintDialog v-if="printing" :doctype="config.doctype" :docname="printing" @close="printing = ''" />
</template>
