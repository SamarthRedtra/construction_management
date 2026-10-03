<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { session } from "@/utils"
import CatalogTabs from "@/components/CatalogTabs.vue"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"
import PriceHistory from "@/components/PriceHistory.vue"

const ctx = computed(() => session.context)
const route = useRoute()
const requests = ref([])
const loading = ref(false)
const detail = ref(null)

async function showDetail(row) {
	try { detail.value = row.purchase_order ? row : await call("get_price_request", { name: row.name }) }
	catch (error) { toastError(error) }
}

async function load() {
	loading.value = true
	try {
		const [prices, orders] = await Promise.all([call("get_price_requests"), call("get_po_price_requests")])
		requests.value = [...orders.map((order) => {
			const proposal = JSON.parse(order.custom_po_price_proposal || "{}")
			const history = JSON.parse(order.custom_po_price_history || "[]")
			if (!proposal.changes && history.length) Object.assign(proposal, history[history.length - 1])
			return { ...order, purchase_order: order.name, status: order.custom_po_price_status,
				item_code: `${proposal.changes?.length || 0} item(s)`,
				requested_by: proposal.requested_by || order.owner, requested_on: proposal.requested_on || order.modified,
				notification_status: order.custom_po_price_notification,
				notification_error: order.custom_po_price_notification_error, proposal }
		}), ...prices]
	}
	catch (error) { toastError(error) }
	finally { loading.value = false }
}

async function decide(row, approved) {
	const comment = approved ? "" : window.prompt("Reason for rejecting this price")
	if (!approved && !comment?.trim()) return
	try {
		const method = row.purchase_order
			? row.status === "Pending Accounts" ? approved ? "approve_accounts_po_price" : "reject_accounts_po_price" : approved ? "approve_po_price" : "reject_po_price"
			: approved ? "approve_price_change" : "reject_price_change"
		const result = await call(method, { name: row.name, comment })
		toast(result.status === "Needs Correction" ? result.reason || "Price or Purchase Order changed; requester must submit a new proposal" : `Price request ${result.status}`)
		await load()
	} catch (error) { toastError(error) }
}

async function retry(row) {
	try { await call(row.purchase_order ? "retry_po_price_notice" : "retry_price_notice", { name: row.name }); toast("Raven notification retry queued"); await load() }
	catch (error) { toastError(error) }
}

function oldPrice(change, currency, supplier) {
	const rate = change.old_active_rate ?? change.old_po_rate
	if (supplier && change.old_active_supplier === "" && change.old_active_item_price)
		return `New supplier price (general fallback ${currency} ${rate})`
	return rate == null ? "New price" : `${currency} ${rate}`
}

onMounted(async () => {
	await load()
	const requested = requests.value.find((row) => row.name === route.query.request)
	if (requested) await showDetail(requested)
})
</script>

<template>
	<PageHeader title="Buying Price Requests" subtitle="CEO decisions and Raven delivery for catalog and Purchase Order prices." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Controlled Catalog', to: '/catalog' }, { label: 'Price requests' }]" />
	<CatalogTabs />
	<section class="cp-card">
		<table class="cp-table">
			<thead><tr><th>Request / item</th><th>Scope</th><th>Rate</th><th>Status</th><th>Requested / decided</th><th>Raven</th><th /></tr></thead>
			<tbody>
				<tr v-for="row in requests" :key="row.name">
					<td><button class="cp-link" @click="showDetail(row)">{{ row.name }}</button><small>{{ row.purchase_order ? 'Purchase Order · ' : '' }}{{ row.item_code }} · {{ row.company }}</small></td>
					<td>{{ row.supplier || "General" }}<small>{{ row.price_list }}</small></td>
					<td><template v-if="row.purchase_order">{{ row.proposal.changes?.map((change) => `${change.item_code}: ${oldPrice(change, row.currency || ctx.currency, row.supplier)} → ${row.currency || ctx.currency} ${change.rate}`).join('; ') || 'Decision recorded' }}</template><template v-else>{{ row.target_item_price ? `${row.currency} ${row.old_rate}` : "New price" }} → <strong>{{ row.currency }} {{ row.proposed_rate }}</strong></template></td>
					<td><span class="cp-pill info">{{ row.status }}</span><small v-if="row.decision_comment">{{ row.decision_comment }}</small></td>
					<td>{{ row.requested_by }}<small>{{ row.requested_on }}</small><small v-if="row.decided_by">{{ row.decided_by }} · {{ row.decided_on }}</small></td>
					<td>{{ row.notification_status || "Pending" }}<small v-if="row.notification_error">{{ row.notification_error }}</small></td>
					<td class="cp-table-actions">
						<button v-if="ctx.can_approve_po_price_accounts && row.purchase_order && row.status === 'Pending Accounts'" class="cp-btn sm" @click="decide(row, true)">Accounts approve</button>
						<button v-if="ctx.can_approve_po_price_accounts && row.purchase_order && row.status === 'Pending Accounts'" class="cp-btn sm" @click="decide(row, false)">Reject</button>
						<button v-if="ctx.can_approve_price_change && row.status === 'Pending CEO' && (!row.purchase_order || row.custom_lpo_type !== 'Manual' || row.docstatus === 1)" class="cp-btn sm" @click="decide(row, true)">Approve</button>
						<RouterLink v-if="row.purchase_order && row.custom_lpo_type === 'Manual' && row.docstatus === 0 && row.status === 'Pending CEO'" :to="`/purchase-orders/${row.name}`" class="cp-btn sm">Use Manual LPO approval</RouterLink>
						<button v-if="ctx.can_approve_price_change && row.status === 'Pending CEO'" class="cp-btn sm" @click="decide(row, false)">Reject</button>
						<button v-if="row.notification_status !== 'Delivered' && (ctx.can_approve_price_change || row.requested_by === ctx.user || ctx.can_override_lpo)" class="cp-btn sm" @click="retry(row)">Retry Raven</button>
					</td>
				</tr>
				<tr v-if="!loading && !requests.length"><td colspan="7" class="cp-empty-row">No buying price requests for this company.</td></tr>
			</tbody>
		</table>
	</section>
	<Modal v-if="detail" :title="detail.name" wide @close="detail = null">
		<p v-if="detail.purchase_order"><strong>Purchase Order:</strong> <RouterLink :to="`/purchase-orders/${detail.name}`">{{ detail.name }}</RouterLink></p>
		<template v-if="detail.purchase_order"><div v-for="change in detail.proposal.changes || []" :key="change.index"><p><strong>{{ change.item_code }}</strong> · {{ detail.supplier || "General" }} · {{ change.price_list }}</p><p>{{ oldPrice(change, detail.currency || ctx.currency, detail.supplier) }} → <strong>{{ detail.currency || ctx.currency }} {{ change.rate }}</strong> · {{ change.reason }}</p><PriceHistory :item-code="change.item_code" :supplier="detail.supplier" :price-list="change.price_list" :company="detail.company" /></div></template>
		<template v-else><p><strong>{{ detail.item_code }}</strong> · {{ detail.supplier || "General" }} · {{ detail.price_list }}</p><p>{{ detail.target_item_price ? `${detail.currency} ${detail.old_rate}` : "New price" }} → <strong>{{ detail.currency }} {{ detail.proposed_rate }}</strong></p><p><strong>Reason:</strong> {{ detail.reason }}</p><PriceHistory :item-code="detail.item_code" :supplier="detail.supplier" :price-list="detail.price_list" :company="detail.company" /></template>
		<p><strong>Decision:</strong> {{ detail.status }}<span v-if="detail.decided_by"> by {{ detail.decided_by }} on {{ detail.decided_on }}</span><span v-if="detail.decision_comment"> — {{ detail.decision_comment }}</span></p>
		<p v-if="detail.result_item_price"><strong>Applied Item Price:</strong> {{ detail.result_item_price }}</p>
		<h3 class="cp-section-title">Raven notification history</h3>
		<ul><li v-for="(event, index) in JSON.parse(detail.notification_history || detail.custom_po_price_history || '[]')" :key="index">{{ event.at }} · {{ event.recipient || event.by || "No recipient" }} · {{ event.status || event.action }}<span v-if="event.error"> — {{ event.error }}</span></li></ul>
	</Modal>
</template>
