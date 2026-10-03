<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { call } from "@/api"
import { DOCTYPES, debounce, docStatusLabel, formatCurrency, formatDate, isOverdue } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"
import PrintDialog from "@/components/PrintDialog.vue"
import StatusPill from "@/components/StatusPill.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import { companyFilters } from "@/utils"

const props = defineProps({ kind: { type: String, required: true } })
const route = useRoute()
const createdOrder = computed(() => props.kind === "orders" ? String(route.query.created || "") : "")
const config = computed(() => DOCTYPES[props.kind])
const rows = ref([])
const total = ref(0)
const search = ref("")
const docstatus = ref("")
const sortBy = ref("modified")
const sortOrder = ref("desc")
const loading = ref(false)
const printing = ref("")
const filters = reactive({ supplier: "", project: "", lpo_type: "", purchase_order: "", warehouse: "", from_warehouse: "", to_warehouse: "", item_code: "", date_from: "", date_to: "" })
function clearFilters() { for (const key of Object.keys(filters)) filters[key] = "" }

async function load(append = false) {
	loading.value = true
	try {
		const result = await call("get_controlled_documents", {
			doctype: config.value.doctype,
			search: search.value,
			docstatus: docstatus.value,
			sort_by: sortBy.value,
			sort_order: sortOrder.value,
			start: append ? rows.value.length : 0,
			page_length: 25,
			...filters,
		})
		rows.value = append ? [...rows.value, ...result.rows] : result.rows
		total.value = result.total_count
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

function rowStatus(row) {
	if (props.kind === "invoices" && isOverdue(row)) return "Overdue"
	return docStatusLabel(row)
}

watch(search, debounce(() => load(), 300))
watch(docstatus, () => load())
watch([sortBy, sortOrder], () => load())
watch(filters, debounce(() => load(), 250))
onMounted(() => load())
</script>

<template>
	<PageHeader :title="config.title" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: config.title }]">
		<template #actions>
			<RouterLink :to="`${config.path}/new`" class="cp-btn primary">New {{ config.single.toLowerCase() }}</RouterLink>
		</template>
	</PageHeader>
	<p v-if="createdOrder" class="cp-hint" role="status">Purchase Order {{ createdOrder }} was created as a draft. Review it below before submitting.</p>

	<div class="cp-filters">
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
	<div v-if="kind !== 'invoices'" class="cp-section" style="padding: 16px; margin-bottom: 16px">
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
		<button type="button" class="cp-link sm" @click="clearFilters">Clear filters</button>
	</div>

	<section class="cp-card">
		<table class="cp-table">
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
				<tr v-for="row in rows" :key="row.name" class="clickable" :class="{ 'cp-new-order-row': row.name === createdOrder }" @click="$router.push(`${config.path}/${row.name}`)">
					<td><strong>{{ row.name }}</strong><small v-if="row.supplier">{{ row.supplier_name || row.supplier }}</small><small v-if="kind === 'orders'">{{ row.custom_lpo_type || (row.custom_is_provisional_po ? 'Open' : 'Standard') }} LPO<template v-if="row.custom_lpo_approval_status"> · {{ row.custom_lpo_approval_status }}</template></small><small v-if="row.custom_supplier_invoice_no">Supplier inv {{ row.custom_supplier_invoice_no }}</small></td>
					<td>{{ row.project || "—" }}<small v-if="row.bill_no">{{ row.bill_no }}</small></td>
					<td v-if="kind === 'receipts'">{{ row.supplier_delivery_note || "—" }}</td>
					<td>{{ formatDate(dateOf(row)) }}<small v-if="row.schedule_date || row.due_date" :class="{ 'cp-overdue': kind === 'invoices' && isOverdue(row) }">Due {{ formatDate(row.schedule_date || row.due_date) }}</small></td>
					<td v-if="kind === 'orders'">
						<div class="cp-progress"><i :style="{ width: `${Math.min(row.per_received || 0, 100)}%` }" /></div>
						<small>{{ Math.round(row.per_received || 0) }}%</small>
					</td>
					<td><StatusPill :status="rowStatus(row)" /></td>
					<td class="num">{{ formatCurrency(kind === 'transfers' ? row.total_outgoing_value : row.grand_total) }}</td>
					<td v-if="kind === 'invoices'" class="num"><strong v-if="row.docstatus === 1">{{ formatCurrency(row.outstanding_amount) }}</strong><span v-else class="cp-muted">—</span></td>
					<td class="num"><button class="cp-icon-button sm" title="Print / PDF" aria-label="Print" @click.stop="printing = row.name"><svg viewBox="0 0 24 24"><path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></svg></button></td>
				</tr>
				<tr v-if="!loading && !rows.length"><td :colspan="kind === 'orders' || kind === 'invoices' || kind === 'receipts' ? 7 : 6" class="cp-empty-row">No {{ config.title.toLowerCase() }} found.</td></tr>
			</tbody>
		</table>
		<footer v-if="rows.length" class="cp-card-foot">
			<span>{{ rows.length }} of {{ total }}</span>
			<button v-if="rows.length < total" class="cp-btn sm" :disabled="loading" @click="load(true)">Load more</button>
		</footer>
	</section>
	<PrintDialog v-if="printing" :doctype="config.doctype" :docname="printing" @close="printing = ''" />
</template>
