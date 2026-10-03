<script setup>
import { onMounted, ref } from "vue"
import { call } from "@/api"
import { toastError } from "@/toast"
import { formatCurrency, formatDate } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"

const rows = ref([])
const loading = ref(false)

async function load() {
	loading.value = true
	try {
		rows.value = (await call("get_lpo_approvals")).rows || []
	} catch (error) {
		toastError(error)
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<template>
	<PageHeader title="LPO Approvals" subtitle="Manual LPOs awaiting Accounts or CEO review" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'LPO Approvals' }]" />
	<div class="cp-section-bar"><h2 class="cp-section-title">Approval queue</h2><button class="cp-btn" @click="load">Refresh</button></div>
	<div class="cp-card">
		<table class="cp-table">
			<thead><tr><th>LPO</th><th>Supplier</th><th>Project</th><th>Status</th><th>Updated</th><th class="num">Value</th></tr></thead>
			<tbody>
				<tr v-for="row in rows" :key="row.name">
					<td><RouterLink :to="`/purchase-orders/${encodeURIComponent(row.name)}`">{{ row.name }}</RouterLink></td>
					<td>{{ row.supplier_name }}</td><td>{{ row.project || '—' }}</td>
					<td>{{ row.custom_lpo_approval_status }}</td><td>{{ formatDate(row.modified) }}</td>
					<td class="num">{{ formatCurrency(row.grand_total, row.currency) }}</td>
				</tr>
				<tr v-if="!loading && !rows.length"><td colspan="6" class="cp-muted">No Manual LPOs are awaiting review.</td></tr>
			</tbody>
		</table>
	</div>
</template>
