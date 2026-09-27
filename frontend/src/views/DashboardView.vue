<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "@/api"
import { formatCurrency, formatDate, session, docStatusLabel } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"
import StatusPill from "@/components/StatusPill.vue"

const ctx = computed(() => session.context)
const openLpos = ref({ rows: [], summary: { open_lpos: 0, pending_value: 0, overdue: 0 } })
const recentOrders = ref([])

const stats = computed(() => {
	const counts = ctx.value.dashboard
	return [
		ctx.value.can_purchase && { label: "Open LPOs", value: openLpos.value.summary.open_lpos, hint: `${openLpos.value.summary.overdue} overdue`, to: "/open-lpos", alert: openLpos.value.summary.overdue > 0 },
		ctx.value.can_purchase && { label: "Pending delivery value", value: formatCurrency(openLpos.value.summary.pending_value), hint: "Across open LPOs", to: "/open-lpos" },
		ctx.value.can_purchase && { label: "Draft purchase orders", value: counts.draft_purchase_orders, hint: `${counts.purchase_orders} active in total`, to: "/purchase-orders" },
		{ label: "Controlled items", value: counts.catalog_items, hint: "Approved Nos catalog", to: "/catalog" },
	].filter(Boolean)
})

onMounted(async () => {
	if (!ctx.value.can_purchase) return
	const [lpos, orders] = await Promise.all([
		call("get_open_lpos", { page_length: 5, open_po_only: 1 }),
		call("get_controlled_documents", { doctype: "Purchase Order", page_length: 6 }),
	])
	openLpos.value = lpos
	recentOrders.value = orders.rows
})
</script>

<template>
	<PageHeader title="Procurement Overview" subtitle="Controlled Nos catalog, project BOQ allocation and standard ERPNext posting." :breadcrumbs="[{ label: 'Procurement' }, { label: 'Overview' }]">
		<template #actions>
			<RouterLink v-if="ctx.can_transfer" to="/transfers/new" class="cp-btn">New transfer</RouterLink>
			<RouterLink v-if="ctx.can_purchase" to="/receipts/new" class="cp-btn">New receipt</RouterLink>
			<RouterLink v-if="ctx.can_purchase" to="/purchase-orders/new" class="cp-btn primary">New purchase order</RouterLink>
		</template>
	</PageHeader>

	<div class="cp-stats">
		<RouterLink v-for="stat in stats" :key="stat.label" :to="stat.to" class="cp-stat" :class="{ alert: stat.alert }">
			<small>{{ stat.label }}</small>
			<strong>{{ stat.value }}</strong>
			<span>{{ stat.hint }}</span>
		</RouterLink>
	</div>

	<div v-if="ctx.can_purchase" class="cp-two-col">
		<section class="cp-card">
			<header class="cp-card-head">
				<h3>Open LPOs — next due</h3>
				<RouterLink to="/open-lpos" class="cp-link">View all</RouterLink>
			</header>
			<table class="cp-table compact">
				<thead><tr><th>LPO</th><th>Due</th><th class="num">Pending</th></tr></thead>
				<tbody>
					<tr v-for="row in openLpos.rows" :key="row.name" class="clickable" @click="$router.push(`/purchase-orders/${row.name}`)">
						<td><strong>{{ row.name }}</strong><small>{{ row.supplier_name || row.supplier }}</small></td>
						<td><span :class="{ 'cp-overdue': row.is_overdue }">{{ formatDate(row.schedule_date) }}</span></td>
						<td class="num">{{ formatCurrency(row.pending_value, row.currency) }}</td>
					</tr>
					<tr v-if="!openLpos.rows.length"><td colspan="3" class="cp-empty-row">No open LPOs. Everything ordered has been received.</td></tr>
				</tbody>
			</table>
		</section>
		<section class="cp-card">
			<header class="cp-card-head">
				<h3>Recent purchase orders</h3>
				<RouterLink to="/purchase-orders" class="cp-link">View all</RouterLink>
			</header>
			<table class="cp-table compact">
				<thead><tr><th>Order</th><th>Status</th><th class="num">Value</th></tr></thead>
				<tbody>
					<tr v-for="row in recentOrders" :key="row.name" class="clickable" @click="$router.push(`/purchase-orders/${row.name}`)">
						<td><strong>{{ row.name }}</strong><small>{{ row.supplier_name || row.supplier }}</small></td>
						<td><StatusPill :status="docStatusLabel(row)" /></td>
						<td class="num">{{ formatCurrency(row.grand_total) }}</td>
					</tr>
					<tr v-if="!recentOrders.length"><td colspan="3" class="cp-empty-row">No controlled purchase orders yet.</td></tr>
				</tbody>
			</table>
		</section>
	</div>
</template>
