<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { session } from "@/utils"
import ApprovalFilterChips from "@/components/ApprovalFilterChips.vue"
import CatalogTabs from "@/components/CatalogTabs.vue"
import CatalogRequestItemEditor from "@/components/CatalogRequestItemEditor.vue"
import CatalogRequestItemReview from "@/components/CatalogRequestItemReview.vue"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"
import { useBulkApproval } from "@/composables/useBulkApproval"

const ctx = computed(() => session.context)
const route = useRoute()
const router = useRouter()
const requests = ref([])
const requestDetail = ref(null)
const approvingRequest = ref("")
const resubmitting = ref(false)
const refreshing = ref(false)
const filters = ref({ status: "", request_origin: "", source: "", kind: "" })

const filterGroups = [
	{
		key: "status",
		label: "Status",
		options: [
			{ value: "Pending Accounts", label: "Pending Accounts" },
			{ value: "Pending CEO", label: "Pending CEO" },
			{ value: "Needs Correction", label: "Needs Correction" },
			{ value: "Approved", label: "Approved" },
		],
	},
	{
		key: "request_origin",
		label: "Origin",
		options: [
			{ value: "Purchase", label: "Purchase" },
			{ value: "Accounts", label: "Accounts" },
		],
	},
	{
		key: "source",
		label: "Source",
		options: [
			{ value: "Manual", label: "Manual" },
			{ value: "Workbook Import", label: "Workbook Import" },
			{ value: "Item Edit", label: "Item Edit" },
		],
	},
	{
		key: "kind",
		label: "Kind",
		options: [
			{ value: "disable", label: "Disable item" },
			{ value: "change", label: "Change" },
		],
	},
]

function canDecide(request) {
	return (request.status === "Pending Accounts" && request.requested_by !== ctx.value.user && ctx.value.can_approve_catalog_accounts)
		|| (request.status === "Pending CEO" && ctx.value.can_approve_catalog_ceo)
}

const bulk = useBulkApproval(canDecide)

const filteredRequests = computed(() => {
	const f = filters.value
	return (requests.value || []).filter((row) => {
		if (f.status && row.status !== f.status) return false
		if (f.request_origin && (row.request_origin || "Purchase") !== f.request_origin) return false
		if (f.source && row.source !== f.source) return false
		if (f.kind === "disable" && !row.is_disable) return false
		if (f.kind === "change" && row.is_disable) return false
		return true
	})
})

async function loadRequests() {
	try {
		requests.value = await call("get_catalog_requests")
	} catch (error) {
		toastError(error)
	}
}

async function refresh() {
	if (refreshing.value) return
	refreshing.value = true
	try {
		await loadRequests()
		if (requestDetail.value?.name) await showRequest({ name: requestDetail.value.name })
	} finally {
		refreshing.value = false
	}
}

async function showRequest(request) {
	try {
		requestDetail.value = await call("get_catalog_request", { name: request.name })
		if (route.query.request !== request.name) await router.replace({ query: { ...route.query, request: request.name } })
	} catch (error) {
		toastError(error)
	}
}

async function closeRequest() {
	requestDetail.value = null
	if (route.query.request) await router.replace({ query: { ...route.query, request: undefined } })
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
	if (resubmitting.value) return
	resubmitting.value = true
	try {
		await call("resubmit_catalog_request", { name: request.name, data: {
			items: request.items, disable_reason: request.disable_reason, expected_modified: request.modified,
		} })
		toast("Catalog request resubmitted")
		await loadRequests()
		if (requestDetail.value?.name === request.name) await showRequest(request)
	} catch (error) {
		toastError(error)
	} finally {
		resubmitting.value = false
	}
}

async function retryPriceNotice(request) {
	try { await call("retry_catalog_price_notice", { name: request.name }); toast("Raven retry queued") }
	catch (error) { toastError(error) }
}

async function bulkApprove() {
	const summary = await bulk.runBulk(filteredRequests.value, "bulk_approve_catalog_requests", {}, { actionLabel: "Approving" })
	if (summary) await loadRequests()
}

async function bulkReject() {
	const comment = window.prompt("Reason for rejection (applied to all selected)")
	if (!comment?.trim()) return
	const summary = await bulk.runBulk(
		filteredRequests.value,
		"bulk_reject_catalog_requests",
		{ comment: comment.trim() },
		{ actionLabel: "Rejecting" },
	)
	if (summary) await loadRequests()
}

onMounted(async () => {
	await loadRequests()
	if (route.query.request) await showRequest({ name: route.query.request })
})
</script>

<template>
	<PageHeader title="Catalog Approval Requests" subtitle="Review catalog changes and follow their approval history." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Controlled Catalog', to: '/catalog' }, { label: 'Approval requests' }]">
		<template #actions>
			<button class="cp-btn" :disabled="refreshing" @click="refresh">{{ refreshing ? "Refreshing…" : "Refresh" }}</button>
		</template>
	</PageHeader>
	<CatalogTabs />

	<section class="cp-card">
		<ApprovalFilterChips v-model="filters" :groups="filterGroups" />
		<div v-if="bulk.hasSelection" class="cp-bulk-bar">
			<strong>{{ bulk.selectedCount }} selected</strong>
			<button class="cp-btn sm primary" :disabled="bulk.busy" @click="bulkApprove">Approve selected</button>
			<button class="cp-btn sm" :disabled="bulk.busy" @click="bulkReject">Reject selected</button>
			<button class="cp-btn sm" :disabled="bulk.busy" @click="bulk.clearSelection()">Clear</button>
		</div>
		<table class="cp-table">
			<thead>
				<tr>
					<th class="cp-check-col">
						<input
							type="checkbox"
							class="cp-check"
							:checked="bulk.allEligibleSelected(filteredRequests)"
							:disabled="!filteredRequests.some(canDecide)"
							@change="bulk.toggleSelectAll(filteredRequests, $event.target.checked)"
						/>
					</th>
					<th>Request</th><th>Requested by</th><th>Status</th><th>Source</th><th />
				</tr>
			</thead>
			<tbody>
				<tr v-for="request in filteredRequests" :key="request.name">
					<td class="cp-check-col">
						<input
							type="checkbox"
							class="cp-check"
							:disabled="!canDecide(request)"
							:checked="bulk.isSelected(request)"
							@change="bulk.toggle(request, $event.target.checked)"
						/>
					</td>
					<td><button class="cp-link" @click="showRequest(request)">{{ request.name }}</button><small>{{ request.company }}</small></td>
					<td>{{ request.requested_by }}</td>
					<td><span class="cp-pill info">{{ request.status }}</span></td>
					<td>{{ request.is_disable ? "Disable item" : request.source }}<small>{{ request.request_origin || "Purchase" }} route</small></td>
					<td class="cp-table-actions">
						<button class="cp-btn sm" @click="showRequest(request)">{{ request.status === 'Needs Correction' && request.requested_by === ctx.user ? 'Edit and Resubmit' : canDecide(request) ? 'Review' : 'View' }}</button>
					</td>
				</tr>
				<tr v-if="!filteredRequests.length"><td colspan="6" class="cp-empty-row">No catalog requests match these filters.</td></tr>
			</tbody>
		</table>
	</section>

	<Modal v-if="requestDetail" :title="requestDetail.name" size="xl" @close="closeRequest">
		<p><span class="cp-pill info">{{ requestDetail.status }}</span> · {{ requestDetail.request_origin || "Purchase" }} route</p>
		<div class="cp-grid-2"><p><strong>Company:</strong> {{ requestDetail.company }}</p><p><strong>Currency:</strong> {{ requestDetail.currency || '—' }}</p><p><strong>Requested by:</strong> {{ requestDetail.requested_by }}</p><p><strong>Source:</strong> {{ requestDetail.source }}</p></div>
		<p v-if="requestDetail.source_file"><a :href="requestDetail.source_file" target="_blank" rel="noopener noreferrer">Open source workbook</a></p>
		<p v-if="requestDetail.rejection_reason"><strong>Correction requested:</strong> {{ requestDetail.rejection_reason }}</p>
		<form v-if="requestDetail.status === 'Needs Correction' && requestDetail.requested_by === ctx.user" id="cp-catalog-correction-form" class="cp-stack" @submit.prevent="resubmit(requestDetail)">
			<p class="cp-hint">Correct the highlighted request. Item Code and request type cannot be changed. Saving immediately restarts its approval route.</p>
			<label v-if="requestDetail.items.length === 1 && requestDetail.items[0].action === 'Disable'" class="cp-field"><span>Disable reason<i>*</i></span><textarea v-model="requestDetail.disable_reason" class="cp-input" rows="3" required /></label>
			<CatalogRequestItemEditor v-for="row in requestDetail.items.filter((item) => item.action !== 'Disable')" :key="row.name" :row="row" :company="requestDetail.company" :allow-uom-edit="requestDetail.source === 'Item Edit'" />
		</form>
		<template v-else>
			<p v-if="requestDetail.disable_reason"><strong>Disable reason:</strong> {{ requestDetail.disable_reason }}</p>
			<h3 class="cp-section-title">Item details · Current vs proposed</h3>
			<CatalogRequestItemReview v-for="(row, index) in requestDetail.items" :key="row.name" :row="row" :current="requestDetail.review?.[row.name] || null" :currency="requestDetail.currency" :initially-open="index === 0" />
		</template>
		<p v-if="requestDetail.price_notification_status">Raven notification: {{ requestDetail.price_notification_status }}<span v-if="requestDetail.price_notification_error"> — {{ requestDetail.price_notification_error }}</span> <button v-if="requestDetail.price_notification_status === 'Failed'" class="cp-btn sm" @click="retryPriceNotice(requestDetail)">Retry Raven</button></p>
		<h3 class="cp-section-title">Approval process</h3>
		<ul><li v-for="log in requestDetail.approval_log" :key="log.name"><strong>{{ log.action }}</strong> · {{ log.actor }} · {{ log.actioned_on }}<template v-if="log.comment"> — {{ log.comment }}</template></li></ul>
		<template #footer>
			<button class="cp-btn" @click="closeRequest">Close</button>
			<button v-if="canDecide(requestDetail)" class="cp-btn" :disabled="Boolean(approvingRequest)" @click="reject(requestDetail)">Reject</button>
			<button v-if="canDecide(requestDetail)" class="cp-btn primary" :disabled="Boolean(approvingRequest)" @click="approve(requestDetail)">{{ approvingRequest ? 'Approving…' : 'Approve after review' }}</button>
			<button v-if="requestDetail.status === 'Needs Correction' && requestDetail.requested_by === ctx.user" form="cp-catalog-correction-form" type="submit" class="cp-btn primary" :disabled="resubmitting">{{ resubmitting ? 'Resubmitting…' : 'Save and Resubmit' }}</button>
		</template>
	</Modal>

	<div v-if="approvingRequest || bulk.busy" class="cp-busy-overlay" role="status" aria-live="assertive" aria-label="Catalog approval in progress">
		<div class="cp-busy-card">
			<span class="cp-spinner" aria-hidden="true" />
			<div>
				<strong v-if="bulk.busy">{{ bulk.progress.label }} {{ bulk.progress.total }} selected…</strong>
				<strong v-else>Approving {{ approvingRequest }}…</strong>
				<p>Applying catalog items and approved prices. This can take a few moments; please keep this page open.</p>
			</div>
		</div>
	</div>
</template>
