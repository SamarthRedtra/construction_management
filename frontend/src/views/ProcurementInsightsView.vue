<script setup>
import { computed, onMounted, ref } from "vue"
import { request } from "@/api"
import { toastError } from "@/toast"
import { DOCTYPES, deskUrl, formatCurrency, formatDate, formatNumber, session } from "@/utils"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"

const METRIC_KEYS = ["ordered", "received", "consumed", "transferred_in", "transferred_out", "other", "on_hand"]

const project = ref("")
const projects = ref([])
const report = ref(null)
const loading = ref(false)
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailRows = ref([])
const detailMeta = ref(null)

const summary = computed(() => report.value?.summary || {})

function reportCurrency() {
	return report.value?.currency || session.context?.currency
}

function metricLabel(key) {
	return report.value?.metrics?.[key]?.label || key.replaceAll("_", " ")
}

function canDrill(value) {
	return !loading.value && Number(value) !== 0
}

function docLink(row) {
	if (row.kind && DOCTYPES[row.kind] && row.name) return `${DOCTYPES[row.kind].path}/${encodeURIComponent(row.name)}`
	return row.desk_url || deskUrl(row.doctype, row.name)
}

function rowHasAmount(row) {
	return row.amount != null && Number(row.amount) !== 0
}

async function openBreakdown(itemRow, metric) {
	if (!canDrill(itemRow[metric])) return
	detailMeta.value = {
		metric,
		label: metricLabel(metric),
		item_code: itemRow.item_code,
		item_name: itemRow.item_name || itemRow.item_code,
	}
	detailRows.value = []
	detailOpen.value = true
	detailLoading.value = true
	try {
		const payload = await request(
			"construction_management.api.procurement_insights.get_procurement_insight_breakdown",
			{ project: project.value, item_code: itemRow.item_code, metric },
			"GET",
		)
		detailRows.value = payload.rows || []
	} catch (error) {
		toastError(error)
		detailOpen.value = false
	} finally {
		detailLoading.value = false
	}
}

async function load() {
	if (!project.value) return
	loading.value = true
	try {
		report.value = await request("construction_management.api.procurement_insights.get_procurement_insights", { project: project.value }, "GET")
	} catch (error) {
		toastError(error)
	} finally {
		loading.value = false
	}
}

onMounted(async () => {
	try {
		projects.value = (await request("construction_management.api.procurement_insights.get_insight_projects", {}, "GET")).rows || []
	} catch (error) {
		toastError(error)
	}
})
</script>

<template>
	<PageHeader title="Procurement Insights" subtitle="Project material status, site stock, and consumption" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Procurement Insights' }]"><template #actions><RouterLink v-if="session.context.can_view_stock_ledger" :to="{ path: '/stock-ledger', query: project ? { project } : {} }" class="cp-btn">View stock ledger</RouterLink></template></PageHeader>
	<section class="cp-section"><div class="cp-grid-3"><label class="cp-field"><span>Project</span><select v-model="project" class="cp-input"><option value="">Select project</option><option v-for="row in projects" :key="row.name" :value="row.name">{{ row.name }} · {{ row.project_name }}</option></select></label><button class="cp-btn brand" :disabled="loading || !project" @click="load">Show report</button></div></section>
	<div v-if="report" class="cp-stats">
		<div v-for="key in METRIC_KEYS" :key="key" class="cp-stat static">
			<small>{{ metricLabel(key) }}</small>
			<strong>{{ formatCurrency(summary[key]?.value ?? 0, reportCurrency()) }}</strong>
			<span>Qty {{ formatNumber(summary[key]?.qty ?? 0) }}</span>
		</div>
	</div>
	<p v-if="report" class="cp-muted cp-stats-hint">Card totals are project value ({{ reportCurrency() }}); table cells are quantities per item.</p>
	<section v-if="report" class="cp-card"><header class="cp-card-head"><h3>Material status · {{ report.project }}</h3></header><table class="cp-table">
		<thead><tr><th>Item</th><th v-for="key in METRIC_KEYS" :key="key" class="num">{{ metricLabel(key) }}</th></tr></thead>
		<tbody>
			<tr v-for="row in report.rows" :key="row.item_code">
				<td>
					<div>{{ row.item_name || row.item_code }}</div>
					<div v-if="row.item_name && row.item_name !== row.item_code" class="cp-muted">{{ row.item_code }}</div>
				</td>
				<td v-for="key in METRIC_KEYS" :key="key" class="num">
					<button
						v-if="canDrill(row[key])"
						type="button"
						class="cp-link-btn"
						@click="openBreakdown(row, key)"
					>{{ formatNumber(row[key]) }}</button>
					<span v-else>{{ formatNumber(row[key]) }}</span>
				</td>
			</tr>
			<tr v-if="!report.rows.length"><td :colspan="METRIC_KEYS.length + 1" class="cp-muted">No project material movements yet.</td></tr>
		</tbody>
	</table></section>

	<Modal
		v-if="detailOpen && detailMeta"
		:title="`${detailMeta.label} · ${detailMeta.item_name}`"
		wide
		@close="detailOpen = false"
	>
		<p v-if="detailLoading" class="cp-muted">Loading details…</p>
		<table v-else class="cp-table">
			<thead>
				<tr>
					<th>Date</th>
					<th>Document</th>
					<th class="num">Qty</th>
					<th v-if="detailRows.some(rowHasAmount)" class="num">Amount</th>
					<th>Warehouse</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(line, index) in detailRows" :key="`${line.name}-${index}`">
					<td>{{ line.posting_date ? formatDate(line.posting_date) : "—" }}</td>
					<td>
						<RouterLink v-if="line.kind && line.name" :to="docLink(line)">{{ line.name }}</RouterLink>
						<a v-else-if="line.name && line.desk_url" :href="line.desk_url" target="_blank" rel="noopener">{{ line.name }}</a>
						<span v-else-if="line.name">{{ line.name }}</span>
						<span v-else class="cp-muted">—</span>
					</td>
					<td class="num">{{ formatNumber(line.qty) }}</td>
					<td v-if="detailRows.some(rowHasAmount)" class="num">{{ rowHasAmount(line) ? formatCurrency(line.amount, reportCurrency()) : "—" }}</td>
					<td>{{ line.warehouse || "—" }}</td>
				</tr>
				<tr v-if="!detailLoading && !detailRows.length"><td :colspan="detailRows.some(rowHasAmount) ? 5 : 4" class="cp-muted">No matching vouchers.</td></tr>
			</tbody>
		</table>
		<template #footer><button class="cp-btn" @click="detailOpen = false">Close</button></template>
	</Modal>
</template>

<style scoped>
.cp-link-btn {
	background: none;
	border: none;
	padding: 0;
	color: var(--cp-brand, #2563eb);
	cursor: pointer;
	text-decoration: underline;
	font: inherit;
}
.cp-stats-hint {
	margin: -8px 0 20px;
	font-size: 12px;
}
</style>
