<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { formatCurrency, formatDate, session } from "@/utils"
import ApprovalFilterChips from "@/components/ApprovalFilterChips.vue"
import PageHeader from "@/components/PageHeader.vue"
import { useBulkApproval } from "@/composables/useBulkApproval"

const ctx = computed(() => session.context)
const rows = ref([])
const loading = ref(false)
const filters = ref({ status: "" })
const acting = ref("")

const filterGroups = [
	{
		key: "status",
		label: "Status",
		options: [
			{ value: "Pending Accounts", label: "Pending Accounts" },
			{ value: "Pending CEO", label: "Pending CEO" },
			{ value: "Needs Correction", label: "Needs Correction" },
		],
	},
]

function canDecide(row) {
	const status = row.custom_lpo_approval_status
	return (status === "Pending Accounts" && ctx.value.can_approve_lpo_accounts)
		|| (status === "Pending CEO" && ctx.value.can_approve_lpo_ceo)
}

const bulk = useBulkApproval(canDecide)

const filteredRows = computed(() => {
	const status = filters.value.status
	if (!status) return rows.value
	return (rows.value || []).filter((row) => row.custom_lpo_approval_status === status)
})

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

async function approveOne(row) {
	if (acting.value) return
	acting.value = row.name
	try {
		const result = await call("approve_lpo", { name: row.name })
		toast(result.approval_status === "Approved" ? `LPO ${row.name} approved and submitted` : `LPO ${row.name} → ${result.approval_status}`)
		await load()
	} catch (error) {
		toastError(error)
	} finally {
		acting.value = ""
	}
}

async function rejectOne(row) {
	const comment = window.prompt("Reason for rejection")
	if (!comment?.trim()) return
	if (acting.value) return
	acting.value = row.name
	try {
		await call("reject_lpo", { name: row.name, comment: comment.trim() })
		toast(`LPO ${row.name} returned for correction`)
		await load()
	} catch (error) {
		toastError(error)
	} finally {
		acting.value = ""
	}
}

async function bulkApprove() {
	const summary = await bulk.runBulk(filteredRows.value, "bulk_approve_lpos", {}, { actionLabel: "Approving" })
	if (summary) await load()
}

async function bulkReject() {
	const comment = window.prompt("Reason for rejection (applied to all selected)")
	if (!comment?.trim()) return
	const summary = await bulk.runBulk(
		filteredRows.value,
		"bulk_reject_lpos",
		{ comment: comment.trim() },
		{ actionLabel: "Rejecting" },
	)
	if (summary) await load()
}

onMounted(load)
</script>

<template>
	<PageHeader title="LPO Approvals" subtitle="Manual LPOs awaiting Accounts or CEO review" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'LPO Approvals' }]" />
	<div class="cp-section-bar"><h2 class="cp-section-title">Approval queue</h2><button class="cp-btn" @click="load">Refresh</button></div>
	<div class="cp-card">
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
							:checked="bulk.allEligibleSelected(filteredRows)"
							:disabled="!filteredRows.some(canDecide)"
							@change="bulk.toggleSelectAll(filteredRows, $event.target.checked)"
						/>
					</th>
					<th>LPO</th><th>Supplier</th><th>Project</th><th>Status</th><th>Updated</th><th class="num">Value</th><th />
				</tr>
			</thead>
			<tbody>
				<tr v-for="row in filteredRows" :key="row.name">
					<td class="cp-check-col">
						<input
							type="checkbox"
							class="cp-check"
							:disabled="!canDecide(row)"
							:checked="bulk.isSelected(row)"
							@change="bulk.toggle(row, $event.target.checked)"
						/>
					</td>
					<td><RouterLink :to="`/purchase-orders/${encodeURIComponent(row.name)}`">{{ row.name }}</RouterLink></td>
					<td>{{ row.supplier_name }}</td><td>{{ row.project || '—' }}</td>
					<td><span class="cp-pill info">{{ row.custom_lpo_approval_status }}</span></td>
					<td>{{ formatDate(row.modified) }}</td>
					<td class="num">{{ formatCurrency(row.grand_total, row.currency) }}</td>
					<td class="cp-table-actions">
						<button v-if="canDecide(row)" class="cp-btn sm primary" :disabled="Boolean(acting) || bulk.busy" @click="approveOne(row)">Approve</button>
						<button v-if="canDecide(row)" class="cp-btn sm" :disabled="Boolean(acting) || bulk.busy" @click="rejectOne(row)">Reject</button>
						<RouterLink :to="`/purchase-orders/${encodeURIComponent(row.name)}`" class="cp-btn sm">Open</RouterLink>
					</td>
				</tr>
				<tr v-if="!loading && !filteredRows.length"><td colspan="8" class="cp-muted">No Manual LPOs match these filters.</td></tr>
			</tbody>
		</table>
	</div>
	<div v-if="bulk.busy || acting" class="cp-busy-overlay" role="status" aria-live="assertive">
		<div class="cp-busy-card">
			<span class="cp-spinner" aria-hidden="true" />
			<div>
				<strong v-if="bulk.busy">{{ bulk.progress.label }} {{ bulk.progress.total }} selected…</strong>
				<strong v-else>Approving {{ acting }}…</strong>
				<p>Keep this page open until the action finishes.</p>
			</div>
		</div>
	</div>
</template>
