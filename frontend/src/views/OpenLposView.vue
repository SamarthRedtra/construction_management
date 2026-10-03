<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call } from "@/api"
import { toastError } from "@/toast"
import { debounce, formatCurrency, formatDate, formatNumber, companyFilters } from "@/utils"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"
import PrintDialog from "@/components/PrintDialog.vue"
import StatusPill from "@/components/StatusPill.vue"

const rows = ref([])
const summary = ref({ open_lpos: 0, pending_value: 0, overdue: 0 })
const filters = ref({ search: "", supplier: "", project: "" })
const overdueOnly = ref(false)
const loading = ref(true)
const printing = ref("")
const totalCount = ref(0)
let requestId = 0

const visibleRows = computed(() => (overdueOnly.value ? rows.value.filter((row) => row.is_overdue) : rows.value))

async function load(more = false) {
	const currentRequest = ++requestId
	loading.value = true
	try {
		const result = await call("get_open_lpos", { ...filters.value, start: more ? rows.value.length : 0, page_length: 50, open_po_only: 1 })
		if (currentRequest !== requestId) return
		rows.value = more ? [...rows.value, ...result.rows] : result.rows
		summary.value = result.summary
		totalCount.value = result.total_count
	} catch (error) {
		if (currentRequest === requestId) toastError(error)
	} finally {
		if (currentRequest === requestId) loading.value = false
	}
}

watch(() => filters.value.search, debounce(() => load(), 300))
watch(() => [filters.value.supplier, filters.value.project], () => load())
onMounted(() => load())
</script>

<template>
	<PageHeader title="Open LPOs" subtitle="Open purchase orders remain available for receipts until closed." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Open LPOs' }]">
		<template #actions>
			<RouterLink to="/receipts/new" class="cp-btn">Receive goods</RouterLink>
			<RouterLink :to="{ path: '/purchase-orders/new', query: { lpo_type: 'Open' } }" class="cp-btn primary">New LPO</RouterLink>
		</template>
	</PageHeader>

	<div class="cp-stats">
		<div class="cp-stat"><small>Open LPOs</small><strong>{{ summary.open_lpos }}</strong><span>Available until closed</span></div>
		<div class="cp-stat"><small>Pending value</small><strong>{{ formatCurrency(summary.pending_value) }}</strong><span>Still to be delivered</span></div>
		<button class="cp-stat" :class="{ alert: summary.overdue, selected: overdueOnly }" @click="overdueOnly = !overdueOnly">
			<small>Overdue</small><strong>{{ summary.overdue }}</strong><span>{{ overdueOnly ? "Showing overdue only" : "Past required-by date" }}</span>
		</button>
	</div>

	<div class="cp-filters">
		<input v-model="filters.search" class="cp-input cp-search" placeholder="Search LPO, supplier or project" />
		<LinkSelect v-model="filters.supplier" doctype="Supplier" placeholder="All suppliers" />
		<LinkSelect v-model="filters.project" doctype="Project" placeholder="All projects" :filters="companyFilters()" />
	</div>

	<section class="cp-card">
		<table class="cp-table">
			<thead>
				<tr><th>LPO</th><th>Project</th><th>Ordered</th><th>Required by</th><th>Received</th><th class="num">Pending qty</th><th class="num">Pending value</th><th></th></tr>
			</thead>
			<tbody>
				<tr v-for="row in visibleRows" :key="row.name" class="clickable" @click="$router.push(`/purchase-orders/${row.name}`)">
					<td><strong>{{ row.name }}</strong> <StatusPill v-if="row.is_open_po" status="Open PO" /><small>{{ row.supplier_name || row.supplier }}</small><small v-if="Number(row.pending_qty) <= 0">Fully received · still open</small></td>
					<td>{{ row.project || "—" }}</td>
					<td>{{ formatDate(row.transaction_date) }}<small>{{ row.age_days }} days ago</small></td>
					<td>
						<span :class="{ 'cp-overdue': row.is_overdue }">{{ formatDate(row.schedule_date) }}</span>
						<StatusPill v-if="row.is_overdue" status="Overdue" />
					</td>
					<td>
						<div class="cp-progress"><i :style="{ width: `${Math.min(row.per_received, 100)}%` }" /></div>
						<small>{{ Math.round(row.per_received) }}% received</small>
					</td>
					<td class="num">{{ formatNumber(row.pending_qty) }}<small>{{ row.line_count }} lines</small></td>
					<td class="num"><strong>{{ formatCurrency(row.pending_value, row.currency) }}</strong></td>
					<td class="num">
						<span class="cp-row-actions">
						<button class="cp-icon-button sm" title="Print / PDF" aria-label="Print" @click.stop="printing = row.name"><svg viewBox="0 0 24 24"><path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></svg></button>
						<RouterLink :to="{ path: '/receipts/new', query: { po: row.name } }" class="cp-btn sm" @click.stop>Receive</RouterLink>
						</span>
					</td>
				</tr>
				<tr v-if="!loading && !visibleRows.length"><td colspan="8" class="cp-empty-row">No open LPOs match these filters.</td></tr>
				<tr v-if="loading"><td colspan="8" class="cp-empty-row">Loading…</td></tr>
			</tbody>
		</table>
		<footer v-if="rows.length" class="cp-card-foot">
			<span>{{ rows.length }} of {{ totalCount }} Open LPOs</span>
			<button v-if="rows.length < totalCount" type="button" class="cp-btn sm" :disabled="loading" @click="load(true)">Load more</button>
		</footer>
	</section>
	<PrintDialog v-if="printing" doctype="Purchase Order" :docname="printing" @close="printing = ''" />
</template>
