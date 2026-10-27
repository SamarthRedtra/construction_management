<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { request } from "@/api"
import { toastError } from "@/toast"
import { formatDate, formatNumber, today } from "@/utils"
import LedgerFilterSelect from "@/components/LedgerFilterSelect.vue"
import PageHeader from "@/components/PageHeader.vue"
import PaginationBar from "@/components/PaginationBar.vue"

const PAGE_SIZE = 100

const route = useRoute()
const receipt = computed(() => String(route.query.receipt || ""))
const filters = reactive({ project: String(route.query.project || ""), item_code: "", warehouse: "", from_date: "", to_date: "" })
const rows = ref([])
const company = ref("")
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const exporting = ref(false)
const resolvedWarehouses = ref([])

function resetToFirstPage() {
	if (page.value !== 1) page.value = 1
	else load()
}

async function load() {
	loading.value = true
	try {
		const result = await request("construction_management.api.procurement_insights.get_stock_ledger", {
			receipt: receipt.value,
			...filters,
			start: (page.value - 1) * PAGE_SIZE,
		}, "GET")
		rows.value = result.rows || []
		company.value = result.company || ""
		total.value = result.total_count || 0
		resolvedWarehouses.value = result.resolved_warehouses || []
		const maxPage = Math.max(1, Math.ceil((result.total_count || 0) / PAGE_SIZE) || 1)
		if (page.value > maxPage) page.value = maxPage
	} catch (error) {
		toastError(error)
	} finally {
		loading.value = false
	}
}

async function exportCsv() {
	exporting.value = true
	try {
		const query = new URLSearchParams()
		for (const [key, value] of Object.entries({ receipt: receipt.value, ...filters })) if (value) query.set(key, value)
		const response = await fetch(`/api/method/construction_management.api.procurement_insights.export_stock_ledger?${query}`, { credentials: "same-origin" })
		if (!response.ok) {
			const payload = await response.json().catch(() => ({}))
			const messages = JSON.parse(payload._server_messages || "[]")
			throw new Error(messages.length ? JSON.parse(messages[0]).message : payload.exception || "Could not export stock ledger")
		}
		const url = URL.createObjectURL(await response.blob())
		const link = document.createElement("a")
		link.href = url
		link.download = `stock-ledger-${today()}.csv`
		link.click()
		setTimeout(() => URL.revokeObjectURL(url), 1000)
	} catch (error) { toastError(error) }
	finally { exporting.value = false }
}

watch(page, () => load())
onMounted(() => load())
</script>

<template>
	<PageHeader title="Stock ledger" :subtitle="receipt ? `Receive Note ${receipt}` : company" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Stock ledger' }]">
		<template #actions><button class="cp-btn" :disabled="exporting" @click="exportCsv">{{ exporting ? 'Exporting…' : 'Export CSV' }}</button></template>
	</PageHeader>
	<section class="cp-section"><div class="cp-grid-3">
		<LedgerFilterSelect v-if="!receipt" v-model="filters.project" field="project" label="Project" />
		<LedgerFilterSelect v-model="filters.item_code" field="item_code" label="Item code" :receipt="receipt" />
		<LedgerFilterSelect v-model="filters.warehouse" field="warehouse" label="Warehouse" :receipt="receipt" />
		<label class="cp-field"><span>From date</span><input v-model="filters.from_date" type="date" class="cp-input" /></label>
		<label class="cp-field"><span>To date</span><input v-model="filters.to_date" type="date" class="cp-input" /></label>
	</div><p v-if="filters.project" class="cp-hint">Project scope: {{ resolvedWarehouses.length ? resolvedWarehouses.map((row) => row.label).join(', ') : 'no active linked warehouses' }}. Warehouse is an optional drill-down.</p><button class="cp-btn brand" :disabled="loading" @click="resetToFirstPage">Apply filters</button></section>
	<div class="cp-card"><table class="cp-table">
		<thead><tr><th>Date</th><th>Item</th><th>Warehouse</th><th>Project</th><th>Voucher</th><th class="num">In</th><th class="num">Out</th><th class="num">Movement value</th><th class="num">Balance qty</th><th class="num">Balance value</th></tr></thead>
		<tbody>
			<tr v-for="row in rows" :key="row.name"><td>{{ formatDate(row.posting_date) }}</td><td>{{ row.item_code }}</td><td>{{ row.warehouse }}</td><td>{{ row.project || '—' }}</td><td>{{ row.voucher_type }} · {{ row.voucher_no }}</td><td class="num">{{ formatNumber(row.in_qty) }}</td><td class="num">{{ formatNumber(row.out_qty) }}</td><td class="num">{{ formatNumber(row.movement_value) }}</td><td class="num">{{ formatNumber(row.qty_after_transaction) }}</td><td class="num">{{ formatNumber(row.valuation_balance) }}</td></tr>
			<tr v-if="!loading && !rows.length"><td colspan="10" class="cp-muted">No stock-ledger entries match these filters.</td></tr>
		</tbody>
	</table>
	<PaginationBar v-model:page="page" :page-size="PAGE_SIZE" :total="total" :loading="loading" />
	</div>
</template>
