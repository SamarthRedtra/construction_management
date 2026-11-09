<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { request } from "@/api"
import { toastError } from "@/toast"
import { formatNumber, session } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"
import ItemPicker from "@/components/ItemPicker.vue"

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const projects = ref([])
const report = ref(null)
const expanded = ref({})

const filters = ref({
	project: "",
	item_code: "",
	warehouse: "",
	stage: "",
	overdue_grn_only: false,
	from_date: "",
	to_date: "",
})

const stageOptions = [
	{ value: "", label: "All stages" },
	{ value: "mr_only", label: "MR only" },
	{ value: "partly_ordered", label: "Partly ordered" },
	{ value: "ordered", label: "Ordered" },
	{ value: "grn_pending", label: "GRN pending (overdue)" },
	{ value: "partly_received", label: "Partly received" },
	{ value: "received", label: "Received" },
	{ value: "transferred", label: "Transferred" },
	{ value: "consumed", label: "Consumed" },
	{ value: "invoiced", label: "Invoiced" },
	{ value: "paid", label: "Paid" },
]

const stageClass = {
	mr_only: "muted",
	partly_ordered: "warn",
	ordered: "info",
	grn_pending: "danger",
	partly_received: "warn",
	received: "ok",
	transferred: "ok",
	consumed: "ok",
	invoiced: "info",
	paid: "ok",
}

const rows = computed(() => report.value?.rows || [])

function deskLink(doctype, name) {
	if (!name) return "#"
	const slug = doctype.toLowerCase().replaceAll(" ", "-")
	return `/app/${slug}/${encodeURIComponent(name)}`
}

function toggle(rowKey) {
	expanded.value = { ...expanded.value, [rowKey]: !expanded.value[rowKey] }
}

function syncQuery() {
	const query = {}
	for (const [key, value] of Object.entries(filters.value)) {
		if (value === false || value === "" || value == null) continue
		query[key] = value === true ? "1" : String(value)
	}
	router.replace({ path: "/lifecycle", query })
}

async function load() {
	loading.value = true
	syncQuery()
	try {
		report.value = await request(
			"construction_management.api.material_lifecycle_tracker.get_material_lifecycle_tracker",
			{
				project: filters.value.project || "",
				item_code: filters.value.item_code || "",
				warehouse: filters.value.warehouse || "",
				stage: filters.value.stage || "",
				overdue_grn_only: filters.value.overdue_grn_only ? 1 : 0,
				from_date: filters.value.from_date || "",
				to_date: filters.value.to_date || "",
				limit: 500,
			},
			"GET",
		)
		expanded.value = {}
	} catch (error) {
		toastError(error)
	} finally {
		loading.value = false
	}
}

function exportCsv() {
	const header = [
		"Project", "Item", "Stage", "MR", "PO", "Supplier", "Required Date",
		"Requested", "Ordered", "Received", "Transferred", "Consumed", "Invoiced", "Paid",
		"Warehouse", "Receipts", "Transfers", "Invoices", "Payments",
	]
	const lines = [header.join(",")]
	for (const row of rows.value) {
		lines.push([
			row.project, row.item_code, row.stage, row.material_request, row.purchase_order, row.supplier,
			row.required_date, row.requested_qty, row.ordered_qty, row.received_qty, row.transferred_qty,
			row.consumed_qty, row.invoiced_qty, row.paid_qty, row.warehouse,
			(row.receipts || []).join(";"), (row.transfers || []).join(";"),
			(row.invoices || []).join(";"), (row.payments || []).join(";"),
		].map((v) => `"${String(v ?? "").replaceAll('"', '""')}"`).join(","))
	}
	const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" })
	const url = URL.createObjectURL(blob)
	const a = document.createElement("a")
	a.href = url
	a.download = `material-lifecycle-${new Date().toISOString().slice(0, 10)}.csv`
	a.click()
	URL.revokeObjectURL(url)
}

onMounted(async () => {
	const q = route.query
	filters.value.project = q.project || ""
	filters.value.item_code = q.item_code || ""
	filters.value.warehouse = q.warehouse || ""
	filters.value.stage = q.stage || ""
	filters.value.overdue_grn_only = q.overdue_grn_only === "1"
	filters.value.from_date = q.from_date || ""
	filters.value.to_date = q.to_date || ""
	try {
		projects.value = (await request("construction_management.api.procurement_insights.get_insight_projects", {}, "GET")).rows || []
	} catch (error) {
		toastError(error)
	}
	if (filters.value.project || filters.value.item_code || filters.value.overdue_grn_only || filters.value.stage) {
		await load()
	}
})

watch(() => session.version, () => {
	report.value = null
})
</script>

<template>
	<PageHeader
		title="Material Lifecycle"
		subtitle="Track material from request through receive, transfer, consumption, invoice and payment"
		:breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Material Lifecycle' }]"
	>
		<template #actions>
			<button class="cp-btn" :disabled="!rows.length" @click="exportCsv">Export CSV</button>
		</template>
	</PageHeader>

	<section class="cp-section">
		<div class="cp-grid-3">
			<label class="cp-field">
				<span>Project</span>
				<select v-model="filters.project" class="cp-input">
					<option value="">All projects</option>
					<option v-for="row in projects" :key="row.name" :value="row.name">{{ row.name }} · {{ row.project_name }}</option>
				</select>
			</label>
			<ItemPicker v-model="filters.item_code" label="Item" :show-code="true" />
			<label class="cp-field">
				<span>Stage</span>
				<select v-model="filters.stage" class="cp-input">
					<option v-for="opt in stageOptions" :key="opt.value || 'all'" :value="opt.value">{{ opt.label }}</option>
				</select>
			</label>
			<label class="cp-field">
				<span>From date</span>
				<input v-model="filters.from_date" type="date" class="cp-input" />
			</label>
			<label class="cp-field">
				<span>To date</span>
				<input v-model="filters.to_date" type="date" class="cp-input" />
			</label>
			<label class="cp-field cp-check">
				<span>Overdue GRN only</span>
				<input v-model="filters.overdue_grn_only" type="checkbox" />
			</label>
		</div>
		<div class="cp-actions-row">
			<button class="cp-btn brand" :disabled="loading" @click="load">{{ loading ? 'Loading…' : 'Show tracker' }}</button>
		</div>
	</section>

	<section v-if="report" class="cp-card">
		<header class="cp-card-head">
			<h3>{{ report.company }} · {{ report.count }} line(s)</h3>
		</header>
		<div class="cp-table-wrap">
			<table class="cp-table lifecycle-table">
				<thead>
					<tr>
						<th></th>
						<th>Item</th>
						<th>Stage</th>
						<th>MR</th>
						<th>PO</th>
						<th>Required</th>
						<th class="num">Req</th>
						<th class="num">Ord</th>
						<th class="num">Recv</th>
						<th class="num">Xfer</th>
						<th class="num">Cons</th>
						<th class="num">Inv</th>
						<th class="num">Paid</th>
						<th>Warehouse</th>
					</tr>
				</thead>
				<tbody>
					<template v-for="row in rows" :key="row.row_key">
						<tr :class="{ overdue: row.overdue_grn }">
							<td>
								<button class="cp-linkish" @click="toggle(row.row_key)">{{ expanded[row.row_key] ? '▾' : '▸' }}</button>
							</td>
							<td>
								<div class="cp-strong">{{ row.item_code }}</div>
								<small class="cp-muted">{{ row.project }} · {{ row.item_name }}</small>
							</td>
							<td><span class="stage-pill" :class="stageClass[row.stage] || 'muted'">{{ row.stage.replaceAll('_', ' ') }}</span></td>
							<td>
								<a v-if="row.material_request" :href="deskLink('Material Request', row.material_request)" target="_blank">{{ row.material_request }}</a>
								<span v-else class="cp-muted">—</span>
							</td>
							<td>
								<a v-if="row.purchase_order" :href="deskLink('Purchase Order', row.purchase_order)" target="_blank">{{ row.purchase_order }}</a>
								<span v-else class="cp-muted">—</span>
							</td>
							<td>{{ row.required_date || '—' }}</td>
							<td class="num">{{ formatNumber(row.requested_qty) }}</td>
							<td class="num">{{ formatNumber(row.ordered_qty) }}</td>
							<td class="num">{{ formatNumber(row.received_qty) }}</td>
							<td class="num">{{ formatNumber(row.transferred_qty) }}</td>
							<td class="num">{{ formatNumber(row.consumed_qty) }}</td>
							<td class="num">{{ formatNumber(row.invoiced_qty) }}</td>
							<td class="num">{{ formatNumber(row.paid_qty) }}</td>
							<td>{{ row.warehouse || '—' }}</td>
						</tr>
						<tr v-if="expanded[row.row_key]" class="timeline-row">
							<td colspan="14">
								<ol class="lifecycle-timeline">
									<li v-for="(ev, idx) in row.timeline || []" :key="idx">
										<strong>{{ ev.label }}</strong>
										<a :href="deskLink(ev.doctype, ev.name)" target="_blank">{{ ev.name }}</a>
										<span class="cp-muted">{{ ev.date || '' }}</span>
									</li>
									<li v-if="!(row.timeline || []).length" class="cp-muted">No linked documents yet.</li>
								</ol>
							</td>
						</tr>
					</template>
					<tr v-if="!rows.length">
						<td colspan="14" class="cp-muted">No lines match these filters.</td>
					</tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<style scoped>
.cp-actions-row { margin-top: 0.75rem; }
.cp-check { display: flex; align-items: center; gap: 0.5rem; }
.cp-table-wrap { overflow-x: auto; }
.lifecycle-table .overdue td { background: color-mix(in srgb, #b42318 8%, transparent); }
.stage-pill {
	display: inline-block;
	padding: 0.15rem 0.45rem;
	border-radius: 999px;
	font-size: 11px;
	text-transform: capitalize;
	white-space: nowrap;
}
.stage-pill.ok { background: #e8f5e9; color: #1b5e20; }
.stage-pill.info { background: #e3f2fd; color: #0d47a1; }
.stage-pill.warn { background: #fff8e1; color: #e65100; }
.stage-pill.danger { background: #fdecea; color: #b71c1c; }
.stage-pill.muted { background: #f3f4f6; color: #4b5563; }
.lifecycle-timeline {
	margin: 0.25rem 0 0.5rem 1rem;
	padding: 0;
	display: grid;
	gap: 0.35rem;
}
.lifecycle-timeline li { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: baseline; }
.cp-linkish { background: none; border: 0; cursor: pointer; font-size: 14px; }
.cp-strong { font-weight: 600; }
</style>
