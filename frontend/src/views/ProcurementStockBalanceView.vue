<script setup>
import { reactive, ref } from "vue"
import { request } from "@/api"
import { toastError } from "@/toast"
import { formatNumber, today } from "@/utils"
import LedgerFilterSelect from "@/components/LedgerFilterSelect.vue"
import PageHeader from "@/components/PageHeader.vue"

const filters = reactive({ project: "", item_code: "", warehouse: "", from_date: "", to_date: "" })
const rows = ref([])
const company = ref("")
const resolvedWarehouses = ref([])
const loading = ref(false)
const exporting = ref(false)

async function load() {
	loading.value = true
	try {
		const result = await request("construction_management.api.procurement_insights.get_stock_balance", filters, "GET")
		rows.value = result.rows || []
		company.value = result.company || ""
		resolvedWarehouses.value = result.resolved_warehouses || []
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
		for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value)
		const response = await fetch(`/api/method/construction_management.api.procurement_insights.export_stock_balance?${query}`, { credentials: "same-origin" })
		if (!response.ok) throw new Error("Could not export stock balance")
		const url = URL.createObjectURL(await response.blob())
		const link = document.createElement("a")
		link.href = url
		link.download = `stock-balance-${today()}.csv`
		link.click()
		setTimeout(() => URL.revokeObjectURL(url), 1000)
	} catch (error) {
		toastError(error)
	} finally {
		exporting.value = false
	}
}
</script>

<template>
	<PageHeader title="Stock balance" :subtitle="company" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Stock balance' }]" ><template #actions><button class="cp-btn" :disabled="exporting" @click="exportCsv">{{ exporting ? 'Exporting…' : 'Export CSV' }}</button></template></PageHeader>
	<section class="cp-section"><div class="cp-grid-3">
		<LedgerFilterSelect v-model="filters.project" field="project" label="Project" />
		<LedgerFilterSelect v-model="filters.item_code" field="item_code" label="Item code" />
		<LedgerFilterSelect v-model="filters.warehouse" field="warehouse" label="Warehouse" />
		<label class="cp-field"><span>From date</span><input v-model="filters.from_date" type="date" class="cp-input" /></label>
		<label class="cp-field"><span>To date</span><input v-model="filters.to_date" type="date" class="cp-input" /></label>
	</div><p v-if="filters.project" class="cp-hint">Project scope: {{ resolvedWarehouses.length ? resolvedWarehouses.map((row) => row.label).join(', ') : 'no active linked warehouses' }}. Warehouse is an optional drill-down.</p><button class="cp-btn brand" :disabled="loading" @click="load">{{ loading ? 'Loading…' : 'Apply filters' }}</button></section>
	<div class="cp-card"><table class="cp-table">
		<thead><tr><th>Item</th><th>UOM</th><th class="num">Opening qty</th><th class="num">Opening value</th><th class="num">In qty</th><th class="num">In value</th><th class="num">Out qty</th><th class="num">Out value</th><th class="num">Balance qty</th><th class="num">Balance value</th></tr></thead>
		<tbody>
			<tr v-for="row in rows" :key="row.item_code"><td>{{ row.item_name || row.item_code }}<small>{{ row.item_code }}</small></td><td>{{ row.stock_uom }}</td><td class="num">{{ formatNumber(row.opening_qty) }}</td><td class="num">{{ formatNumber(row.opening_value) }}</td><td class="num">{{ formatNumber(row.in_qty) }}</td><td class="num">{{ formatNumber(row.in_value) }}</td><td class="num">{{ formatNumber(row.out_qty) }}</td><td class="num">{{ formatNumber(row.out_value) }}</td><td class="num">{{ formatNumber(row.balance_qty) }}</td><td class="num">{{ formatNumber(row.balance_value) }}</td></tr>
			<tr v-if="!loading && !rows.length"><td colspan="10" class="cp-muted">Apply filters to view stock balances.</td></tr>
		</tbody>
	</table></div>
</template>
