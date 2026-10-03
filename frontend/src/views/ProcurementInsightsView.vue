<script setup>
import { computed, onMounted, ref } from "vue"
import { request } from "@/api"
import { toastError } from "@/toast"
import { formatNumber, session } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"

const project = ref("")
const projects = ref([])
const report = ref(null)
const loading = ref(false)
const totals = computed(() => {
	const result = { ordered: 0, received: 0, consumed: 0, transferred_in: 0, transferred_out: 0, on_hand: 0 }
	for (const row of report.value?.rows || []) for (const key of Object.keys(result)) result[key] += Number(row[key]) || 0
	return result
})

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
	<div v-if="report" class="cp-stats"><div v-for="(value, key) in totals" :key="key" class="cp-stat static"><small>{{ key.replaceAll('_', ' ') }}</small><strong>{{ formatNumber(value) }}</strong></div></div>
	<section v-if="report" class="cp-card"><header class="cp-card-head"><h3>Material status · {{ report.project }}</h3></header><table class="cp-table">
		<thead><tr><th>Item</th><th class="num">Ordered</th><th class="num">Received</th><th class="num">Consumed</th><th class="num">Transfer in</th><th class="num">Transfer out</th><th class="num">Other</th><th class="num">On hand</th></tr></thead>
		<tbody><tr v-for="row in report.rows" :key="row.item_code"><td>{{ row.item_code }}</td><td class="num">{{ formatNumber(row.ordered) }}</td><td class="num">{{ formatNumber(row.received) }}</td><td class="num">{{ formatNumber(row.consumed) }}</td><td class="num">{{ formatNumber(row.transferred_in) }}</td><td class="num">{{ formatNumber(row.transferred_out) }}</td><td class="num">{{ formatNumber(row.other) }}</td><td class="num">{{ formatNumber(row.on_hand) }}</td></tr>
		<tr v-if="!report.rows.length"><td colspan="8" class="cp-muted">No project material movements yet.</td></tr></tbody>
	</table></section>
</template>
