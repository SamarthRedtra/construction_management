<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { session } from "@/utils"
import CatalogTabs from "@/components/CatalogTabs.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"

const ctx = computed(() => session.context)
const requests = ref([])
const requestDetail = ref(null)
const approvingRequest = ref("")

async function loadRequests() {
	try {
		requests.value = await call("get_catalog_requests")
	} catch (error) {
		toastError(error)
	}
}

async function showRequest(request) {
	try {
		requestDetail.value = await call("get_catalog_request", { name: request.name })
	} catch (error) {
		toastError(error)
	}
}

async function approve(request) {
	if (approvingRequest.value) return
	approvingRequest.value = request.name
	try {
		await call("approve_catalog_request", { name: request.name })
		toast("Catalog request approved")
		await loadRequests()
		if (requestDetail.value?.name === request.name) await showRequest(request)
	} catch (error) {
		toastError(error)
	} finally {
		approvingRequest.value = ""
	}
}

async function reject(request) {
	const comment = window.prompt("Reason for rejection")
	if (!comment) return
	try {
		await call("reject_catalog_request", { name: request.name, comment })
		toast("Catalog request returned for correction")
		await loadRequests()
		if (requestDetail.value?.name === request.name) await showRequest(request)
	} catch (error) {
		toastError(error)
	}
}

async function resubmit(request) {
	try {
		await call("resubmit_catalog_request", { name: request.name, data: { items: request.items } })
		toast("Catalog request resubmitted")
		await loadRequests()
		if (requestDetail.value?.name === request.name) await showRequest(request)
	} catch (error) {
		toastError(error)
	}
}

async function retryPriceNotice(request) {
	try { await call("retry_catalog_price_notice", { name: request.name }); toast("Raven retry queued") }
	catch (error) { toastError(error) }
}

onMounted(loadRequests)
</script>

<template>
	<PageHeader title="Catalog Approval Requests" subtitle="Review catalog changes and follow their approval history." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Controlled Catalog', to: '/catalog' }, { label: 'Approval requests' }]" />
	<CatalogTabs />

	<section class="cp-card">
		<table class="cp-table">
			<thead><tr><th>Request</th><th>Requested by</th><th>Status</th><th>Source</th><th /></tr></thead>
			<tbody>
				<tr v-for="request in requests" :key="request.name">
					<td><button class="cp-link" @click="showRequest(request)">{{ request.name }}</button><small>{{ request.company }}</small></td>
					<td>{{ request.requested_by }}</td>
					<td><span class="cp-pill info">{{ request.status }}</span></td>
					<td>{{ request.source }}</td>
					<td class="cp-table-actions">
						<button class="cp-btn sm" @click="showRequest(request)">View</button>
						<button v-if="ctx.can_approve_catalog && request.status.startsWith('Pending') && !(request.status === 'Pending CEO' && request.has_price_change && !ctx.can_approve_price_change)" class="cp-btn sm" :disabled="Boolean(approvingRequest)" @click="approve(request)">{{ approvingRequest === request.name ? "Approving…" : "Approve" }}</button>
						<button v-if="ctx.can_approve_catalog && request.status.startsWith('Pending') && !(request.status === 'Pending CEO' && request.has_price_change && !ctx.can_approve_price_change)" class="cp-btn sm" :disabled="Boolean(approvingRequest)" @click="reject(request)">Reject</button>
						<button v-if="request.status === 'Needs Correction' && request.requested_by === ctx.user" class="cp-btn sm" @click="showRequest(request)">Correct</button>
					</td>
				</tr>
				<tr v-if="!requests.length"><td colspan="5" class="cp-empty-row">No catalog requests.</td></tr>
			</tbody>
		</table>
	</section>

	<Modal v-if="requestDetail" :title="requestDetail.name" wide @close="requestDetail = null">
		<p><span class="cp-pill info">{{ requestDetail.status }}</span><span v-if="requestDetail.rejection_reason"> · {{ requestDetail.rejection_reason }}</span></p>
		<p v-if="requestDetail.price_notification_status">CEO price notification: {{ requestDetail.price_notification_status }}<span v-if="requestDetail.price_notification_error"> — {{ requestDetail.price_notification_error }}</span> <button v-if="requestDetail.price_notification_status === 'Failed'" class="cp-btn sm" @click="retryPriceNotice(requestDetail)">Retry Raven</button></p>
		<table class="cp-table"><thead><tr><th>Description</th><th>Type</th><th>UOM</th><th>Supplier</th><th>Rate</th><th>Action</th><th>Catalog item</th></tr></thead><tbody><tr v-for="row in requestDetail.items" :key="row.name"><td>{{ row.item_name }}</td><td>{{ row.item_type }}</td><td>{{ row.stock_uom || "Nos" }}</td><td><LinkSelect v-if="requestDetail.status === 'Needs Correction' && requestDetail.requested_by === ctx.user" v-model="row.supplier" doctype="Supplier" :required="true" /><span v-else>{{ row.supplier || "—" }}</span></td><td>{{ row.rate }}</td><td>{{ row.action }}</td><td>{{ row.result_item || "Awaiting approval" }}</td></tr></tbody></table>
		<h3 class="cp-section-title">Approval process</h3>
		<ul><li v-for="log in requestDetail.approval_log" :key="log.name"><strong>{{ log.action }}</strong> · {{ log.actor }} · {{ log.actioned_on }}<template v-if="log.comment"> — {{ log.comment }}</template></li></ul>
		<template v-if="requestDetail.status === 'Needs Correction' && requestDetail.requested_by === ctx.user" #footer>
			<button class="cp-btn primary" @click="resubmit(requestDetail)">Resubmit for approval</button>
		</template>
	</Modal>

	<div v-if="approvingRequest" class="cp-busy-overlay" role="status" aria-live="assertive" aria-label="Catalog approval in progress">
		<div class="cp-busy-card">
			<span class="cp-spinner" aria-hidden="true" />
			<div>
				<strong>Approving {{ approvingRequest }}…</strong>
				<p>Applying catalog items and approved prices. This can take a few moments; please keep this page open.</p>
			</div>
		</div>
	</div>
</template>
