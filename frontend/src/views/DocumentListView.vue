<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call } from "@/api"
import { DOCTYPES, debounce, docStatusLabel, formatCurrency, formatDate, isOverdue } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"
import PrintDialog from "@/components/PrintDialog.vue"
import StatusPill from "@/components/StatusPill.vue"

const props = defineProps({ kind: { type: String, required: true } })
const config = computed(() => DOCTYPES[props.kind])
const rows = ref([])
const total = ref(0)
const search = ref("")
const docstatus = ref("")
const loading = ref(false)
const printing = ref("")

async function load(append = false) {
	loading.value = true
	try {
		const result = await call("get_controlled_documents", {
			doctype: config.value.doctype,
			search: search.value,
			docstatus: docstatus.value,
			start: append ? rows.value.length : 0,
			page_length: 25,
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
])

function rowStatus(row) {
	if (props.kind === "invoices" && isOverdue(row)) return "Overdue"
	return docStatusLabel(row)
}

watch(search, debounce(() => load(), 300))
watch(docstatus, () => load())
onMounted(() => load())
</script>

<template>
	<PageHeader :title="config.title" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: config.title }]">
		<template #actions>
			<RouterLink :to="`${config.path}/new`" class="cp-btn primary">New {{ config.single.toLowerCase() }}</RouterLink>
		</template>
	</PageHeader>

	<div class="cp-filters">
		<input v-model="search" class="cp-input cp-search" :placeholder="kind === 'invoices' ? 'Search by ID, supplier, supplier invoice no or project' : `Search ${config.title.toLowerCase()} by ID, supplier or project`" />
		<div class="cp-segmented">
			<button v-for="tab in filterTabs" :key="tab.value" :class="{ active: docstatus === tab.value }" @click="docstatus = tab.value">{{ tab.label }}</button>
		</div>
	</div>

	<section class="cp-card">
		<table class="cp-table">
			<thead>
				<tr>
					<th>{{ config.single }}</th>
					<th>Project</th>
					<th>Date</th>
					<th v-if="kind === 'orders'">Received</th>
					<th>Status</th>
					<th class="num">Value</th>
					<th v-if="kind === 'invoices'" class="num">Outstanding</th>
					<th style="width: 48px" />
				</tr>
			</thead>
			<tbody>
				<tr v-for="row in rows" :key="row.name" class="clickable" @click="$router.push(`${config.path}/${row.name}`)">
					<td><strong>{{ row.name }}</strong><small v-if="row.supplier">{{ row.supplier_name || row.supplier }}</small><small v-if="row.custom_supplier_invoice_no">Supplier inv {{ row.custom_supplier_invoice_no }}</small></td>
					<td>{{ row.project || "—" }}<small v-if="row.bill_no">{{ row.bill_no }}</small></td>
					<td>{{ formatDate(dateOf(row)) }}<small v-if="row.schedule_date || row.due_date" :class="{ 'cp-overdue': kind === 'invoices' && isOverdue(row) }">Due {{ formatDate(row.schedule_date || row.due_date) }}</small></td>
					<td v-if="kind === 'orders'">
						<div class="cp-progress"><i :style="{ width: `${Math.min(row.per_received || 0, 100)}%` }" /></div>
						<small>{{ Math.round(row.per_received || 0) }}%</small>
					</td>
					<td><StatusPill :status="rowStatus(row)" /></td>
					<td class="num">{{ formatCurrency(row.grand_total) }}</td>
					<td v-if="kind === 'invoices'" class="num"><strong v-if="row.docstatus === 1">{{ formatCurrency(row.outstanding_amount) }}</strong><span v-else class="cp-muted">—</span></td>
					<td class="num"><button class="cp-icon-button sm" title="Print / PDF" aria-label="Print" @click.stop="printing = row.name"><svg viewBox="0 0 24 24"><path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></svg></button></td>
				</tr>
				<tr v-if="!loading && !rows.length"><td :colspan="kind === 'orders' || kind === 'invoices' ? 7 : 6" class="cp-empty-row">No {{ config.title.toLowerCase() }} found.</td></tr>
			</tbody>
		</table>
		<footer v-if="rows.length" class="cp-card-foot">
			<span>{{ rows.length }} of {{ total }}</span>
			<button v-if="rows.length < total" class="cp-btn sm" :disabled="loading" @click="load(true)">Load more</button>
		</footer>
	</section>
	<PrintDialog v-if="printing" :doctype="config.doctype" :docname="printing" @close="printing = ''" />
</template>
