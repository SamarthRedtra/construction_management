<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { useRoute } from "vue-router"
import { request } from "@/api"
import { toastError } from "@/toast"
import { formatDate, formatNumber, today } from "@/utils"
import LedgerFilterSelect from "@/components/LedgerFilterSelect.vue"
import PageHeader from "@/components/PageHeader.vue"

const route = useRoute()
const receipt = computed(() => String(route.query.receipt || ""))
const filters = reactive({ project: String(route.query.project || ""), item_code: "", warehouse: "", from_date: "", to_date: "" })
const rows = ref([])
const company = ref("")
const loading = ref(false)
const hasMore = ref(false)
const exporting = ref(false)

async function load(append = false) {
	loading.value = true
	try {
		const result = await request("construction_management.api.procurement_insights.get_stock_ledger", { receipt: receipt.value, ...filters, start: append ? rows.value.length : 0 }, "GET")
		rows.value = append ? [...rows.value, ...(result.rows || [])] : result.rows || []
		company.value = result.company || ""
		hasMore.value = result.has_more
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
	</div><button class="cp-btn brand" :disabled="loading" @click="load()">Apply filters</button></section>
	<div class="cp-card"><table class="cp-table">
		<thead><tr><th>Date</th><th>Item</th><th>Warehouse</th><th>Project</th><th>Voucher</th><th class="num">Movement</th><th class="num">Balance</th></tr></thead>
		<tbody>
			<tr v-for="row in rows" :key="row.name"><td>{{ formatDate(row.posting_date) }}</td><td>{{ row.item_code }}</td><td>{{ row.warehouse }}</td><td>{{ row.project || '—' }}</td><td>{{ row.voucher_type }} · {{ row.voucher_no }}</td><td class="num">{{ formatNumber(row.actual_qty) }}</td><td class="num">{{ formatNumber(row.qty_after_transaction) }}</td></tr>
			<tr v-if="!loading && !rows.length"><td colspan="7" class="cp-muted">No stock-ledger entries match these filters.</td></tr>
		</tbody>
	</table><footer v-if="hasMore" class="cp-card-foot"><button class="cp-btn sm" :disabled="loading" @click="load(true)">Load more</button></footer></div>
</template>
